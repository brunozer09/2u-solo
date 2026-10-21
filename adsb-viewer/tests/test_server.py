import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from src.server import criar_servidor
from src.store import AircraftStore
from src.telemetry import PacoteTelemetria
from src.telemetry_schema import carregar_schema
from src.telemetry_store import TelemetryStore


def _pacote(i):
    return PacoteTelemetria(
        campos={"id": str(i), "millis": i * 1000, "alt_baro": 100.0 - i}, brutos=(), recebido_em=1000.0 + i
    )


class ServidorBase(unittest.TestCase):
    ping = None
    com_telemetria = True

    @classmethod
    def setUpClass(cls):
        cls.tstore = TelemetryStore()
        cls.schema = carregar_schema()
        cls.chamadas_ping = []

        def enviar_ping():
            cls.chamadas_ping.append(1)
            return cls.ping_retorno

        cls.ping_retorno = True
        cls.servidor = criar_servidor(
            AircraftStore(),
            port=0,
            telemetria=cls.tstore if cls.com_telemetria else None,
            schema=cls.schema if cls.com_telemetria else None,
            enviar_ping=enviar_ping if cls.ping else None,
        )
        cls.base = f"http://127.0.0.1:{cls.servidor.server_address[1]}"
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.tstore.encerrar()
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def get(self, caminho):
        return urllib.request.urlopen(self.base + caminho, timeout=5)

    def get_json(self, caminho):
        with self.get(caminho) as r:
            return json.loads(r.read())

    def post(self, caminho, headers=None):
        req = urllib.request.Request(self.base + caminho, data=b"", method="POST", headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())


class TestServidorComTelemetria(ServidorBase):
    ping = True

    def test_paginas_estaticas_e_mime(self):
        with self.get("/") as r:
            self.assertIn("text/html", r.headers["Content-Type"])
        with self.get("/telemetria/") as r:
            self.assertIn("text/html", r.headers["Content-Type"])
        with self.get("/telemetria/dashboard.css") as r:
            self.assertIn("text/css", r.headers["Content-Type"])
        with self.get("/telemetria/js/main.js") as r:
            self.assertIn("text/javascript", r.headers["Content-Type"])
        with self.get("/telemetria/model.obj") as r:
            self.assertIn("text/plain", r.headers["Content-Type"])
            self.assertTrue(r.read().startswith(b"#"))

    def test_assets_compartilhados(self):
        with self.get("/assets/logo.png") as r:
            self.assertEqual(r.headers["Content-Type"], "image/png")

    def test_assets_nao_escapa_da_pasta(self):
        for caminho in ("/assets/../src/main.py", "/assets/%2e%2e/src/main.py", "/assets/../../launcher.py"):
            with self.subTest(caminho=caminho), self.assertRaises(urllib.error.HTTPError):
                self.get(caminho)

    def test_schema(self):
        d = self.get_json("/api/telemetry/schema")
        self.assertEqual(len(d["campos"]), 21)
        self.assertEqual(d["layout"]["graficos"][0]["id"], "altitude")

    def test_latest_vazio_e_com_pacote(self):
        self.assertIsNone(self.get_json("/api/telemetry/latest")["pacote"])
        self.tstore.publicar(_pacote(1))
        d = self.get_json("/api/telemetry/latest")
        self.assertEqual(d["pacote"]["id"], "1")
        self.assertEqual(d["total"], 1)

    def test_health_inclui_telemetria(self):
        d = self.get_json("/api/health")
        self.assertTrue(d["ok"])
        self.assertIn("pacotes", d["telemetria"])

    def test_aircraft_continua_funcionando(self):
        d = self.get_json("/api/aircraft")
        self.assertEqual(d["aircraft"], [])

    def test_rota_telemetria_inexistente(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/telemetry/nada")
        self.assertEqual(ctx.exception.code, 404)

    def test_stream_sse_backlog_e_pacote_ao_vivo(self):
        self.tstore.publicar(_pacote(2))
        resp = self.get("/api/telemetry/stream")
        try:
            self.assertIn("text/event-stream", resp.headers["Content-Type"])
            eventos = []

            def ler_evento():
                bloco = []
                while True:
                    linha = resp.readline().decode("utf-8")
                    if linha in ("\n", "\r\n"):
                        if bloco:
                            return bloco
                        continue
                    bloco.append(linha.rstrip("\r\n"))

            # 1) retry, 2) backlog
            while True:
                bloco = ler_evento()
                if bloco[0].startswith("event: backlog"):
                    break
            dados = json.loads(bloco[1][len("data: "):])
            self.assertTrue(len(dados["pacotes"]) >= 1)
            self.assertIn("idade_ultimo_s", dados)

            # 3) pacote publicado depois chega como evento padrao (sem 'event:')
            self.tstore.publicar(_pacote(99))
            bloco = ler_evento()
            self.assertTrue(bloco[0].startswith("data: "))
            vivo = json.loads(bloco[0][len("data: "):])
            self.assertEqual(vivo["id"], "99")
            self.assertIn("seq", vivo)
        finally:
            resp.close()

    def test_ping_ok(self):
        self.__class__.ping_retorno = True
        status, corpo = self.post("/api/telemetry/ping")
        self.assertEqual((status, corpo["ok"]), (200, True))
        self.assertTrue(self.chamadas_ping)

    def test_ping_porta_indisponivel(self):
        self.__class__.ping_retorno = False
        status, corpo = self.post("/api/telemetry/ping")
        self.assertEqual(status, 503)
        self.assertFalse(corpo["ok"])
        self.__class__.ping_retorno = True

    def test_ping_bloqueia_origem_externa(self):
        n = len(self.chamadas_ping)
        status, _ = self.post("/api/telemetry/ping", {"Origin": "http://site-malicioso.example"})
        self.assertEqual(status, 403)
        self.assertEqual(len(self.chamadas_ping), n)  # nada foi enviado a serial

    def test_ping_aceita_mesma_origem(self):
        host = self.base.replace("http://", "")
        status, _ = self.post("/api/telemetry/ping", {"Origin": self.base, "Host": host})
        self.assertEqual(status, 200)

    def test_post_em_rota_desconhecida(self):
        status, _ = self.post("/api/outra")
        self.assertEqual(status, 404)


class TestServidorSemSerial(ServidorBase):
    ping = False

    def test_ping_sem_serial_da_conflito_claro(self):
        status, corpo = self.post("/api/telemetry/ping")
        self.assertEqual(status, 409)
        self.assertIn("--serial", corpo["erro"])


class TestServidorSemTelemetria(ServidorBase):
    com_telemetria = False
    ping = False

    def test_rotas_de_telemetria_respondem_404_json(self):
        for caminho in ("/api/telemetry/schema", "/api/telemetry/stream", "/api/telemetry/latest"):
            with self.subTest(caminho=caminho), self.assertRaises(urllib.error.HTTPError) as ctx:
                self.get(caminho)
            self.assertEqual(ctx.exception.code, 404)

    def test_health_sem_bloco_de_telemetria(self):
        self.assertNotIn("telemetria", self.get_json("/api/health"))


if __name__ == "__main__":
    unittest.main()
