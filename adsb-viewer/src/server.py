"""
server.py

Servidor HTTP minimo, usando apenas a biblioteca padrao (sem Flask/
FastAPI/etc - CONTEXT.md 5 pede para minimizar dependencias externas),
responsavel por:

1. Servir os arquivos estaticos do front-end:
     /              mapa + tabela ADS-B (frontend/index.html)
     /telemetria/   painel de telemetria da CanSat (frontend/telemetria/)
     /assets/...    imagens compartilhadas (adsb_viewer/assets)
2. ADS-B:   GET /api/aircraft - snapshot do AircraftStore, consumido por
   polling (ver app.js: simples e tolerante a quedas do enlace).
3. Telemetria (so se configurada em run_server):
     GET  /api/telemetry/schema  contrato dos campos/layout (JSON)
     GET  /api/telemetry/latest  ultimo pacote + contadores (JSON)
     GET  /api/telemetry/stream  Server-Sent Events: historico recente
                                 (evento 'backlog') + cada pacote novo
     POST /api/telemetry/ping    envia 'P' pela serial (se a fonte for serial)

A telemetria usa SSE (e nao polling) porque aqui cada pacote importa para
os graficos; o navegador reconecta sozinho e, ao reconectar, recebe o
historico recente de novo (TelemetryStore).
"""

import json
import queue
import time
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

from .log import log
from .store import AircraftStore
from .telemetry_schema import SchemaTelemetria
from .telemetry_store import ENCERRAR, TelemetryStore

PING_SSE_SEGUNDOS = 10.0
RAIZ_PROJETO = Path(__file__).resolve().parent.parent


class VisualizadorHandler(SimpleHTTPRequestHandler):
    """Serve o front-end estatico e a API /api/*.

    As dependencias sao injetadas via functools.partial na hora de
    instanciar o servidor (ver run_server abaixo).
    """

    store: AircraftStore

    # Tipos MIME explicitos: no Windows o registro do sistema as vezes
    # mapeia .js para text/plain, o que faz o navegador RECUSAR modulos ES
    # (<script type="module">) e folhas de estilo.
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".obj": "text/plain; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
    }

    def __init__(
        self,
        *args,
        store: AircraftStore,
        diretorio_frontend: Path,
        diretorio_assets: Optional[Path] = None,
        telemetria: Optional[TelemetryStore] = None,
        schema: Optional[SchemaTelemetria] = None,
        enviar_ping: Optional[Callable[[], bool]] = None,
        **kwargs,
    ):
        self.store = store
        self.diretorio_assets = diretorio_assets
        self.telemetria = telemetria
        self.schema = schema
        self.enviar_ping = enviar_ping
        super().__init__(*args, directory=str(diretorio_frontend), **kwargs)

    # ------------------------------------------------------------------
    # roteamento
    # ------------------------------------------------------------------

    def translate_path(self, path: str) -> str:
        """Mapeia /assets/* para a pasta de assets (fora de frontend/)."""
        caminho = urlsplit(path).path
        if self.diretorio_assets is not None and caminho.startswith("/assets/"):
            original = self.directory
            self.directory = str(self.diretorio_assets)
            try:
                return super().translate_path(caminho[len("/assets"):])
            finally:
                self.directory = original
        return super().translate_path(path)

    def do_GET(self):  # noqa: N802 (nome exigido pela stdlib)
        caminho = urlsplit(self.path).path

        if caminho == "/api/aircraft":
            self._responder_api_aircraft()
            return
        if caminho == "/api/health":
            self._responder_health()
            return
        if caminho.startswith("/api/telemetry/"):
            self._responder_api_telemetria(caminho)
            return
        super().do_GET()

    def do_POST(self):  # noqa: N802
        caminho = urlsplit(self.path).path
        if caminho == "/api/telemetry/ping":
            self._responder_ping()
            return
        self._responder_json({"erro": "nao encontrado"}, HTTPStatus.NOT_FOUND)

    # ------------------------------------------------------------------
    # ADS-B
    # ------------------------------------------------------------------

    def _responder_api_aircraft(self) -> None:
        agora = time.time()
        payload = {
            "server_time": agora,
            "stale_after": self.store.stale_after,
            "remove_after": self.store.remove_after,
            "aircraft": self.store.snapshot(agora=agora),
        }
        self._responder_json(payload)

    def _responder_health(self) -> None:
        payload = {"ok": True, "server_time": time.time()}
        if self.telemetria is not None:
            payload["telemetria"] = {
                "pacotes": self.telemetria.total,
                "idade_ultimo_s": self.telemetria.idade_ultimo(),
                "clientes_stream": self.telemetria.assinantes,
            }
        self._responder_json(payload)

    # ------------------------------------------------------------------
    # telemetria
    # ------------------------------------------------------------------

    def _responder_api_telemetria(self, caminho: str) -> None:
        if self.telemetria is None or self.schema is None:
            self._responder_json({"erro": "telemetria nao configurada"}, HTTPStatus.NOT_FOUND)
            return

        if caminho == "/api/telemetry/schema":
            self._responder_json(self.schema.para_dict())
        elif caminho == "/api/telemetry/latest":
            self._responder_json(
                {
                    "server_time": time.time(),
                    "total": self.telemetria.total,
                    "idade_ultimo_s": self.telemetria.idade_ultimo(),
                    "pacote": self.telemetria.ultimo(),
                }
            )
        elif caminho == "/api/telemetry/stream":
            self._responder_stream_telemetria()
        else:
            self._responder_json({"erro": "nao encontrado"}, HTTPStatus.NOT_FOUND)

    @staticmethod
    def _evento_sse(dados, evento: Optional[str] = None) -> bytes:
        cabecalho = f"event: {evento}\n" if evento else ""
        corpo = json.dumps(dados, ensure_ascii=False, allow_nan=False)
        return f"{cabecalho}data: {corpo}\n\n".encode("utf-8")

    def _responder_stream_telemetria(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        fila, backlog = self.telemetria.assinar()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            # O historico vai num unico evento: o navegador o processa de
            # uma vez e o painel nao pisca "telemetria recebida" por pacote antigo.
            self.wfile.write(
                self._evento_sse(
                    {
                        "pacotes": backlog,
                        "idade_ultimo_s": self.telemetria.idade_ultimo(),
                    },
                    evento="backlog",
                )
            )
            self.wfile.flush()

            while True:
                try:
                    item = fila.get(timeout=PING_SSE_SEGUNDOS)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")  # mantem a conexao viva
                    self.wfile.flush()
                    continue
                if item is ENCERRAR:
                    break
                self.wfile.write(self._evento_sse(item))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            pass  # navegador fechou a aba / reconectou
        finally:
            self.telemetria.cancelar(fila)

    def _origem_confiavel(self) -> bool:
        """Barra POSTs vindos de OUTRAS paginas abertas no navegador
        (um site qualquer nao deve conseguir mandar comandos a CanSat)."""
        origem = self.headers.get("Origin")
        if origem is None:
            return True  # curl, scripts locais
        return urlsplit(origem).netloc == self.headers.get("Host")

    def _responder_ping(self) -> None:
        # Descarta o corpo (se houver) para nao deixar bytes pendentes.
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            tamanho = 0
        if tamanho > 0:
            self.rfile.read(min(tamanho, 4096))

        if not self._origem_confiavel():
            self._responder_json({"ok": False, "erro": "origem nao permitida"}, HTTPStatus.FORBIDDEN)
            return
        if self.enviar_ping is None:
            self._responder_json(
                {"ok": False, "erro": "a fonte de dados atual nao permite envio (use --serial)"},
                HTTPStatus.CONFLICT,
            )
            return
        if not self.enviar_ping():
            self._responder_json(
                {"ok": False, "erro": "porta serial indisponivel no momento"},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        log("Ping 'P' enviado pela serial")
        self._responder_json({"ok": True})

    # ------------------------------------------------------------------
    # utilitarios
    # ------------------------------------------------------------------

    def _responder_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        corpo = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Reaproveita o padrao [LOG]/[DEBUG] do restante do projeto em
        # vez do formato default do BaseHTTPRequestHandler.
        log(f"HTTP {self.address_string()} - {format % args}")


def criar_servidor(
    store: AircraftStore,
    host: str = "127.0.0.1",
    port: int = 8000,
    diretorio_frontend: Optional[Path] = None,
    diretorio_assets: Optional[Path] = None,
    telemetria: Optional[TelemetryStore] = None,
    schema: Optional[SchemaTelemetria] = None,
    enviar_ping: Optional[Callable[[], bool]] = None,
) -> ThreadingHTTPServer:
    """Monta o servidor sem inicia-lo (os testes usam port=0)."""
    if diretorio_frontend is None:
        diretorio_frontend = RAIZ_PROJETO / "frontend"
    if diretorio_assets is None:
        diretorio_assets = RAIZ_PROJETO / "assets"

    handler_cls = partial(
        VisualizadorHandler,
        store=store,
        diretorio_frontend=diretorio_frontend,
        diretorio_assets=diretorio_assets,
        telemetria=telemetria,
        schema=schema,
        enviar_ping=enviar_ping,
    )
    return ThreadingHTTPServer((host, port), handler_cls)


def run_server(
    store: AircraftStore,
    host: str = "127.0.0.1",
    port: int = 8000,
    diretorio_frontend: Optional[Path] = None,
    diretorio_assets: Optional[Path] = None,
    telemetria: Optional[TelemetryStore] = None,
    schema: Optional[SchemaTelemetria] = None,
    enviar_ping: Optional[Callable[[], bool]] = None,
    ao_iniciar: Optional[Callable[[str], None]] = None,
) -> None:
    servidor = criar_servidor(
        store, host, port, diretorio_frontend, diretorio_assets, telemetria, schema, enviar_ping
    )
    url = f"http://{host}:{port}"
    log(f"Visualizador disponivel em {url}")
    if telemetria is not None:
        log(f"Painel de telemetria em {url}/telemetria/")
    if ao_iniciar is not None:
        ao_iniciar(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        log("Encerrando servidor (Ctrl+C)...")
    finally:
        if telemetria is not None:
            telemetria.encerrar()
        servidor.server_close()
