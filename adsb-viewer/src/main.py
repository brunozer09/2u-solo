"""
main.py

Ponto de entrada do visualizador. Junta:

    fonte de linhas (stdin | tcp | udp | replay | serial)
        |-- 'Msg:' ... 'Checksum:'  -> telemetria -> TelemetryStore (SSE) + CSV
        `-- 'adsb:...'              -> parser     -> AircraftStore
                                                      |
                                              servidor HTTP (mapa + painel)

Uso:

    python -m src.main --replay sample_data/example_telemetria.log --replay-loop
    python -m src.main --serial /dev/ttyUSB0 --open
    python -m src.main --stdin
    python -m src.main --tcp 127.0.0.1:5005
    python -m src.main --udp 0.0.0.0:5005
"""

import argparse
import threading
import webbrowser
from pathlib import Path
from typing import Iterator, List, Optional

from .csv_log import RegistroCsvTelemetria
from .log import debug, error, log
from .parser import parse_line
from .sources import SerialLink, replay_source, stdin_source, tcp_source, udp_source
from .server import run_server
from .store import AircraftStore
from .telemetry_pipeline import ProcessadorTelemetria
from .telemetry_schema import CAMINHO_PADRAO as SCHEMA_PADRAO, carregar_schema
from .telemetry_store import TelemetryStore

DIRETORIO_CSV_PADRAO = Path(__file__).resolve().parent.parent / "launches"


def ingest_loop(
    fonte: Iterator[str],
    store: AircraftStore,
    telemetria: Optional[ProcessadorTelemetria] = None,
) -> None:
    """Consome a fonte de linhas indefinidamente e roteia cada linha:
    pacote de telemetria (multi-linha) -> `telemetria`; o resto -> parse ADS-B
    + upsert. Uma linha invalida nunca derruba a ingestao (CONTEXT.md 2.2)."""
    total_linhas = 0
    total_aceitas = 0
    for linha in fonte:
        total_linhas += 1

        if telemetria is not None and telemetria.processar_linha(linha):
            continue

        atualizacao = parse_line(linha)
        if atualizacao is None:
            continue
        store.upsert(atualizacao)
        total_aceitas += 1
        if total_aceitas % 25 == 0:
            debug(f"{total_aceitas}/{total_linhas} linhas aceitas ate agora")


def _parse_host_port(valor: str) -> tuple[str, int]:
    if ":" not in valor:
        raise argparse.ArgumentTypeError("formato esperado HOST:PORT, ex.: 127.0.0.1:5005")
    host, _, porta_str = valor.rpartition(":")
    try:
        porta = int(porta_str)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"porta invalida em '{valor}'") from exc
    return host, porta


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Estacao de solo: visualizador de sinais ADS-B via satelite (mapa + "
            "tabela, linhas 'adsb:icao,lat,lon,alt,air_speed') e painel de "
            "telemetria da CanSat (pacotes 'Msg:' ... 'Checksum:')."
        )
    )

    fonte = parser.add_mutually_exclusive_group(required=True)
    fonte.add_argument(
        "--stdin", action="store_true", help="Le as linhas da entrada padrao."
    )
    fonte.add_argument(
        "--tcp",
        metavar="HOST:PORT",
        type=_parse_host_port,
        help="Conecta como cliente TCP em HOST:PORT e le as linhas de la.",
    )
    fonte.add_argument(
        "--udp",
        metavar="HOST:PORT",
        type=_parse_host_port,
        help=(
            "Abre um socket UDP e faz bind em HOST:PORT (ex.: 0.0.0.0:5005 "
            "para aceitar de qualquer interface), recebendo datagramas "
            "enviados pela estacao de solo."
        ),
    )
    fonte.add_argument(
        "--serial",
        metavar="PORTA SERIAL",
        type=str,
        help=(
            "Usa uma conexao serial como fonte"
            ),
    )
    fonte.add_argument(
        "--replay",
        metavar="ARQUIVO",
        type=str,
        help="Le as linhas de um arquivo de captura (para desenvolvimento/teste).",
    )

    parser.add_argument(
        "--replay-rate",
        type=float,
        default=5.0,
        help="Linhas por segundo ao usar --replay (0 = sem pausas). Padrao: 5.",
    )
    parser.add_argument(
        "--replay-loop",
        action="store_true",
        help="Reinicia o arquivo de --replay ao chegar no final.",
    )

    parser.add_argument(
        "--stale-after",
        type=float,
        default=30.0,
        help="Segundos sem atualizacao ate uma aeronave ser marcada como 'stale'. Padrao: 30.",
    )
    parser.add_argument(
        "--remove-after",
        type=float,
        default=300.0,
        help=(
            "Segundos sem atualizacao ate uma aeronave ser removida do store "
            "(some do mapa e da tabela). Use 0 para desativar a remocao. Padrao: 300."
        ),
    )

    parser.add_argument("--host", default="127.0.0.1", help="Host do servidor HTTP local.")
    parser.add_argument("--port", type=int, default=8000, help="Porta do servidor HTTP local.")
    parser.add_argument(
        "--open",
        action="store_true",
        help="Abre o navegador na pagina inicial ao subir o servidor.",
    )

    telemetria = parser.add_argument_group("telemetria da CanSat")
    telemetria.add_argument(
        "--no-telemetry",
        action="store_true",
        help="Desativa a telemetria (so ADS-B).",
    )
    telemetria.add_argument(
        "--telemetry-schema",
        metavar="ARQUIVO",
        type=Path,
        default=SCHEMA_PADRAO,
        help=f"JSON com os campos/layout da telemetria. Padrao: {SCHEMA_PADRAO.name} em config/.",
    )
    telemetria.add_argument(
        "--telemetry-history",
        type=int,
        default=240,
        help=(
            "Quantos pacotes recentes o servidor guarda para reconstruir os graficos "
            "quando a pagina e' aberta/recarregada. Padrao: 240."
        ),
    )
    telemetria.add_argument(
        "--csv-dir",
        type=Path,
        default=DIRETORIO_CSV_PADRAO,
        help="Pasta dos CSVs de telemetria (um arquivo novo por execucao). Padrao: launches/.",
    )
    telemetria.add_argument(
        "--no-csv",
        action="store_true",
        help="Nao grava o CSV de telemetria.",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    args = build_arg_parser().parse_args(argv)
    log("Comecando execucao")

    remove_after = None if args.remove_after == 0 else args.remove_after
    try:
        store = AircraftStore(stale_after=args.stale_after, remove_after=remove_after)
    except ValueError as e:
        error(str(e))
        raise SystemExit(1) from e

    # --- telemetria (opcional) ------------------------------------------------
    schema = None
    telemetria_store = None
    processador = None
    csv_log = None
    if not args.no_telemetry:
        try:
            schema = carregar_schema(args.telemetry_schema)
            telemetria_store = TelemetryStore(historico_max=args.telemetry_history)
        except ValueError as e:
            error(str(e))
            raise SystemExit(1) from e

        if not args.no_csv:
            csv_log = RegistroCsvTelemetria(
                args.csv_dir, list(schema.chaves_serial) + ["t_pc_iso"]
            )
        processador = ProcessadorTelemetria(schema, telemetria_store, csv_log)
        log(f"Telemetria ativa: {len(schema.chaves_serial)} campos por pacote")

    # --- fonte de linhas ------------------------------------------------------
    enviar_ping = None
    if args.stdin:
        log("Fonte: stdin")
        fonte = stdin_source()
    elif args.tcp:
        host, porta = args.tcp
        log(f"Fonte: TCP {host}:{porta}")
        fonte = tcp_source(host, porta)
    elif args.udp:
        host, porta = args.udp
        log(f"Fonte: UDP {host}:{porta}")
        fonte = udp_source(host, porta)
    elif args.serial:
        log(f"Fonte: Serial {args.serial}")
        link = SerialLink(args.serial)
        fonte = link.linhas()
        enviar_ping = lambda: link.enviar(b"P")  # noqa: E731 - botao PING do painel
    else:
        caminho = Path(args.replay)
        if not caminho.exists():
            error(f"Arquivo de replay nao encontrado: {caminho}")
            raise SystemExit(1)
        log(f"Fonte: replay de {caminho} ({args.replay_rate} linhas/s, loop={args.replay_loop})")
        fonte = replay_source(str(caminho), linhas_por_segundo=args.replay_rate, repetir=args.replay_loop)

    thread_ingestao = threading.Thread(
        target=ingest_loop, args=(fonte, store, processador), daemon=True, name="ingest"
    )
    thread_ingestao.start()

    def ao_iniciar(url: str) -> None:
        if not args.open:
            return
        try:
            webbrowser.open(url)
        except Exception:  # sem navegador/DISPLAY: nao e' erro fatal
            pass

    try:
        run_server(
            store,
            host=args.host,
            port=args.port,
            telemetria=telemetria_store,
            schema=schema,
            enviar_ping=enviar_ping,
            ao_iniciar=ao_iniciar,
        )
    finally:
        if csv_log is not None:
            csv_log.fechar()
    log("Encerrando execucao")


if __name__ == "__main__":
    main()
