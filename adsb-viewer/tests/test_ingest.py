import tempfile
import unittest
from pathlib import Path

from src.csv_log import RegistroCsvTelemetria
from src.main import ingest_loop
from src.store import AircraftStore
from src.telemetry_pipeline import ProcessadorTelemetria
from src.telemetry_schema import carregar_schema
from src.telemetry_store import TelemetryStore

AMOSTRA = Path(__file__).resolve().parent.parent / "sample_data" / "example_telemetria.log"


def _linhas(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        return [l.rstrip("\n") for l in arquivo]


class TestIngestMisto(unittest.TestCase):
    def test_log_de_exemplo_alimenta_telemetria_e_adsb(self):
        schema = carregar_schema()
        tstore = TelemetryStore(historico_max=500)
        astore = AircraftStore()
        with tempfile.TemporaryDirectory() as tmp:
            csv_log = RegistroCsvTelemetria(Path(tmp), list(schema.chaves_serial) + ["t_pc_iso"])
            proc = ProcessadorTelemetria(schema, tstore, csv_log, imprimir_pacotes=False)
            ingest_loop(iter(_linhas(AMOSTRA)), astore, proc)
            csv_log.fechar()

            self.assertEqual(tstore.total, 60)
            self.assertEqual(len(astore), 3)  # e49c07, e4a5b4, c0ffee
            hist = tstore.historico()
            self.assertEqual(hist[0]["id"], "1")
            self.assertEqual(hist[-1]["id"], "60")
            self.assertEqual(hist[16]["checksum"], 0)  # o pacote 17 foi gerado com checksum falho
            self.assertTrue(all(p["checksum"] in (0, 1) for p in hist))
            self.assertLess(hist[-1]["alt_baro"], hist[0]["alt_baro"])  # descendo
            linhas_csv = csv_log.caminho.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(linhas_csv), 61)  # cabecalho + 60 pacotes

    def test_adsb_dentro_de_pacote_nao_corrompe_nenhum_dos_dois(self):
        schema = carregar_schema()
        tstore = TelemetryStore()
        astore = AircraftStore()
        proc = ProcessadorTelemetria(schema, tstore, None, imprimir_pacotes=False)
        linhas = [
            "Msg:-90,7,64", "Id:1", "Millis:1000", "Bat:7.4,150",
            "adsb:aaaaaa,-22.5,-46.2,10000,300.0",      # intercalada no meio do pacote
            "Pos:-23.2,-45.9,600", "Baro:930,650,22", "Acel:0,0,1", "Giro:1,2,3", "Checksum:1",
        ]
        ingest_loop(iter(linhas), astore, proc)
        self.assertEqual(tstore.total, 1)
        self.assertEqual(tstore.ultimo()["alt_gps"], 600)
        self.assertEqual(len(astore), 1)

    def test_sem_processador_o_comportamento_antigo_e_preservado(self):
        astore = AircraftStore()
        ingest_loop(iter(["Msg:1,2,3", "adsb:aaaaaa,1,2,3,4", "lixo"]), astore)
        self.assertEqual(len(astore), 1)


if __name__ == "__main__":
    unittest.main()
