import queue
import threading
import unittest

from src.telemetry import PacoteTelemetria
from src.telemetry_store import ENCERRAR, TelemetryStore


def _pacote(i: int, t: float = 100.0) -> PacoteTelemetria:
    return PacoteTelemetria(campos={"id": str(i)}, brutos=(str(i),), recebido_em=t + i)


class TestTelemetryStore(unittest.TestCase):
    def test_publicar_numera_e_guarda_historico_limitado(self):
        s = TelemetryStore(historico_max=3)
        for i in range(1, 6):
            reg = s.publicar(_pacote(i))
            self.assertEqual(reg["seq"], i)
        self.assertEqual(s.total, 5)
        self.assertEqual([r["seq"] for r in s.historico()], [3, 4, 5])
        self.assertEqual(s.ultimo()["id"], "5")

    def test_idade_do_ultimo(self):
        s = TelemetryStore()
        self.assertIsNone(s.idade_ultimo())
        s.publicar(_pacote(1, t=100.0))  # recebido_em = 101
        self.assertAlmostEqual(s.idade_ultimo(agora=104.5), 3.5)
        self.assertEqual(s.idade_ultimo(agora=50.0), 0.0)  # relogio nunca da negativo

    def test_assinante_recebe_backlog_e_depois_ao_vivo_sem_perda_nem_duplicata(self):
        s = TelemetryStore()
        s.publicar(_pacote(1))
        s.publicar(_pacote(2))
        fila, backlog = s.assinar()
        self.assertEqual([r["seq"] for r in backlog], [1, 2])
        s.publicar(_pacote(3))
        self.assertEqual(fila.get_nowait()["seq"], 3)
        with self.assertRaises(queue.Empty):
            fila.get_nowait()

    def test_cancelar_para_de_entregar(self):
        s = TelemetryStore()
        fila, _ = s.assinar()
        self.assertEqual(s.assinantes, 1)
        s.cancelar(fila)
        s.cancelar(fila)  # idempotente
        self.assertEqual(s.assinantes, 0)
        s.publicar(_pacote(1))
        self.assertTrue(fila.empty())

    def test_fila_cheia_descarta_o_mais_antigo_e_nao_bloqueia(self):
        s = TelemetryStore(fila_max=3)
        fila, _ = s.assinar()  # ninguem consome
        for i in range(1, 8):
            s.publicar(_pacote(i))  # nao pode travar
        restantes = [fila.get_nowait()["seq"] for _ in range(fila.qsize())]
        self.assertEqual(restantes, [5, 6, 7])

    def test_encerrar_acorda_assinantes(self):
        s = TelemetryStore()
        fila, _ = s.assinar()
        s.encerrar()
        self.assertIs(fila.get_nowait(), ENCERRAR)

    def test_publicacao_concorrente(self):
        s = TelemetryStore(historico_max=1000)
        fila, _ = s.assinar()

        def produtor(base):
            for i in range(100):
                s.publicar(_pacote(base + i))

        ts = [threading.Thread(target=produtor, args=(k * 1000,)) for k in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(s.total, 400)
        seqs = sorted(fila.get_nowait()["seq"] for _ in range(fila.qsize()))
        self.assertEqual(seqs, list(range(1, 401)))

    def test_historico_max_invalido(self):
        with self.assertRaises(ValueError):
            TelemetryStore(historico_max=0)


if __name__ == "__main__":
    unittest.main()
