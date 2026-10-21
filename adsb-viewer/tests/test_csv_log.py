import csv
import tempfile
import unittest
from pathlib import Path

from src.csv_log import RegistroCsvTelemetria, proximo_arquivo_csv

CAB = ["a", "b", "t_pc_iso"]


def _ler(caminho):
    with open(caminho, newline="", encoding="utf-8") as f:
        return list(csv.reader(f, delimiter=";"))


class TestProximoArquivo(unittest.TestCase):
    def test_numeracao_e_criacao_da_pasta(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp) / "novo" / "launches"
            self.assertEqual(proximo_arquivo_csv(pasta).name, "telemetria1.csv")
            (pasta / "telemetria1.csv").write_text("x")
            (pasta / "telemetria7.csv").write_text("x")
            (pasta / "telemetriaX.csv").write_text("x")   # ignorado
            (pasta / "outro.csv").write_text("x")         # ignorado
            self.assertEqual(proximo_arquivo_csv(pasta).name, "telemetria8.csv")


class TestRegistroCsv(unittest.TestCase):
    def test_nao_cria_arquivo_antes_do_primeiro_pacote(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = RegistroCsvTelemetria(Path(tmp), CAB)
            self.assertIsNone(r.caminho)
            self.assertEqual(list(Path(tmp).iterdir()), [])
            r.fechar()

    def test_cabecalho_e_linhas_anexadas_e_descarregadas(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = RegistroCsvTelemetria(Path(tmp), CAB)
            self.assertTrue(r.registrar(["1", "2"], "2026-01-01T00:00:00"))
            # sem fechar: o flush ja deve ter gravado em disco
            self.assertEqual(_ler(r.caminho), [CAB, ["1", "2", "2026-01-01T00:00:00"]])
            r.registrar(["3", "NaN"], "2026-01-01T00:00:01")
            self.assertEqual(len(_ler(r.caminho)), 3)
            self.assertEqual(_ler(r.caminho)[2][1], "NaN")
            r.fechar()

    def test_execucoes_diferentes_nao_se_sobrescrevem(self):
        with tempfile.TemporaryDirectory() as tmp:
            r1 = RegistroCsvTelemetria(Path(tmp), CAB)
            r1.registrar(["1", "2"], "t")
            r2 = RegistroCsvTelemetria(Path(tmp), CAB)
            r2.registrar(["9", "9"], "t")
            self.assertNotEqual(r1.caminho, r2.caminho)
            self.assertEqual(_ler(r1.caminho)[1][0], "1")
            r1.fechar(); r2.fechar()

    def test_erro_de_disco_nao_levanta(self):
        with tempfile.TemporaryDirectory() as tmp:
            arquivo_no_lugar_da_pasta = Path(tmp) / "bloqueado"
            arquivo_no_lugar_da_pasta.write_text("sou um arquivo")
            r = RegistroCsvTelemetria(arquivo_no_lugar_da_pasta, CAB)
            self.assertFalse(r.registrar(["1", "2"], "t"))  # sem excecao
            self.assertFalse(r.registrar(["1", "2"], "t"))
            r.fechar()


if __name__ == "__main__":
    unittest.main()
