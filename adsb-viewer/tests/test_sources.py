import socket
import threading
import time
import unittest

from src.sources import udp_source


def _porta_livre() -> int:
    """Pede ao SO uma porta de loopback livre (bind com port=0), para
    o teste nao depender de uma porta fixa nem colidir com outro
    processo/teste rodando em paralelo."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _receber_em_thread(fonte, quantidade: int, timeout: float = 2.0):
    """Avanca o generator numa thread separada e devolve as linhas
    recebidas. Necessario porque o corpo de udp_source() (incluindo o
    bind()) so comeca a executar no primeiro next() - se o envio
    (sendto) acontecesse antes desse primeiro next() na mesma thread,
    o datagrama seria perdido (ninguem ainda fez bind na porta) e o
    teste travaria esperando um datagrama que nunca chega."""
    linhas = []
    pronto = threading.Event()

    def alvo():
        for _ in range(quantidade):
            linhas.append(next(fonte))
            pronto.set()

    t = threading.Thread(target=alvo, daemon=True)
    t.start()
    time.sleep(0.1)  # da tempo do bind() acontecer antes de qualquer envio
    return t, linhas


class TestUdpSource(unittest.TestCase):
    def test_recebe_uma_linha_por_datagrama(self):
        porta = _porta_livre()
        fonte = udp_source("127.0.0.1", porta)
        t, linhas = _receber_em_thread(fonte, quantidade=1)

        remetente = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            linha_esperada = "adsb:e49c07,-22.5,-46.2,18000,370.4"
            remetente.sendto(linha_esperada.encode("utf-8"), ("127.0.0.1", porta))
            t.join(timeout=2.0)
            self.assertFalse(t.is_alive(), "timeout esperando o datagrama")
            self.assertEqual(linhas, [linha_esperada])
        finally:
            remetente.close()

    def test_datagrama_com_multiplas_linhas_e_dividido(self):
        porta = _porta_livre()
        fonte = udp_source("127.0.0.1", porta)
        t, linhas = _receber_em_thread(fonte, quantidade=2)

        remetente = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            payload = "adsb:aaaaaa,1,2,3,4\nadsb:bbbbbb,5,6,7,8\n"
            remetente.sendto(payload.encode("utf-8"), ("127.0.0.1", porta))
            t.join(timeout=2.0)
            self.assertFalse(t.is_alive(), "timeout esperando os datagramas")
            self.assertEqual(
                linhas, ["adsb:aaaaaa,1,2,3,4", "adsb:bbbbbb,5,6,7,8"]
            )
        finally:
            remetente.close()

    def test_datagrama_vazio_e_ignorado(self):
        porta = _porta_livre()
        fonte = udp_source("127.0.0.1", porta)
        t, linhas = _receber_em_thread(fonte, quantidade=1)

        remetente = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            remetente.sendto(b"", ("127.0.0.1", porta))
            remetente.sendto(b"adsb:cccccc,1,2,3,4", ("127.0.0.1", porta))
            t.join(timeout=2.0)
            self.assertFalse(t.is_alive(), "timeout esperando o datagrama")
            self.assertEqual(linhas, ["adsb:cccccc,1,2,3,4"])
        finally:
            remetente.close()


if __name__ == "__main__":
    unittest.main()
