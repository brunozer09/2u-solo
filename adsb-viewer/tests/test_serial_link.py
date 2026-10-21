import threading
import time
import unittest

from src.sources import SerialLink


class FakeSerial:
    """Porta falsa: entrega 'entradas' em ordem; None simula timeout; excecao simula queda."""

    def __init__(self, entradas):
        self._entradas = list(entradas)
        self.escritos = []
        self.fechada = False
        self.buffer_limpo = False

    def reset_input_buffer(self):
        self.buffer_limpo = True

    def readline(self):
        if not self._entradas:
            time.sleep(0.01)
            return b""
        item = self._entradas.pop(0)
        if isinstance(item, Exception):
            raise item
        return b"" if item is None else item

    def write(self, dados):
        self.escritos.append(dados)

    def flush(self):
        pass

    def close(self):
        self.fechada = True


def _link(portas):
    fila = list(portas)

    def abrir():
        item = fila.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return SerialLink("FAKE", reconectar_apos=0.01, espera_apos_abrir=0, abrir=abrir)


class TestSerialLink(unittest.TestCase):
    def test_gera_linhas_limpas_ignora_timeout_e_vazias(self):
        porta = FakeSerial([b"Msg:1,2,3\r\n", None, b"   \n", "adsb:x,1,2,3,4\n".encode()])
        link = _link([porta])
        it = link.linhas()
        self.assertEqual(next(it), "Msg:1,2,3")
        self.assertEqual(next(it), "adsb:x,1,2,3,4")
        self.assertTrue(porta.buffer_limpo)
        it.close()
        self.assertTrue(porta.fechada)
        self.assertFalse(link.conectado)

    def test_enviar_so_funciona_com_porta_aberta(self):
        porta = FakeSerial([b"a\n"])
        link = _link([porta])
        self.assertFalse(link.enviar(b"P"))  # ainda nao abriu
        it = link.linhas()
        next(it)
        self.assertTrue(link.conectado)
        self.assertTrue(link.enviar(b"P"))
        self.assertEqual(porta.escritos, [b"P"])
        it.close()
        self.assertFalse(link.enviar(b"P"))

    def test_reabre_apos_queda_e_apos_falha_ao_abrir(self):
        p1 = FakeSerial([b"um\n", OSError("USB removido")])
        p2 = FakeSerial([b"dois\n"])
        link = _link([OSError("porta ocupada"), p1, p2])
        it = link.linhas()
        self.assertEqual(next(it), "um")      # 1a tentativa falhou, 2a abriu
        self.assertEqual(next(it), "dois")    # p1 caiu, reabriu em p2
        self.assertTrue(p1.fechada)
        it.close()

    def test_envio_concorrente_com_leitura(self):
        porta = FakeSerial([b"x\n"] * 5)
        link = _link([porta])
        it = link.linhas()
        next(it)
        resultados = []
        ts = [threading.Thread(target=lambda: resultados.append(link.enviar(b"P"))) for _ in range(5)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(resultados, [True] * 5)
        it.close()


if __name__ == "__main__":
    unittest.main()
