"""
sources.py

Fontes de ingestao de linhas de texto para o visualizador.

O transporte real entre a estacao de solo e o visualizador NAO esta
definido nos artefatos de referencia (CONTEXT.md 7). Por isso, assim
como o projeto anterior citado no CONTEXT.md (que tinha opcoes
--stdin/--tcp/--replay), este modulo oferece tres formas de alimentar
o mesmo pipeline de parsing + store, para que a fonte real possa ser
plugada mais tarde sem mudar o resto do app:

- stdin_source(): le linha a linha da entrada padrao. Util para ligar
  este processo a qualquer coisa que escreva no stdout dele via pipe
  (ex.: um script da estacao de solo, `cat arquivo | python -m src.main --stdin`).
- tcp_source(): conecta como CLIENTE TCP num host:porta (ex.: um
  servico da estacao de solo que exponha as linhas via socket) e
  reconecta automaticamente se a conexao cair - relevante dado que o
  enlace via satelite pode ter latencia variavel e quedas (CONTEXT.md 5).
- udp_source(): abre um socket UDP e faz bind em host:porta (aqui o
  visualizador atua como SERVIDOR, nao como cliente - a estacao de
  solo apenas envia datagramas para esse endereco, sem handshake
  previo). Cada datagrama e' tratado como uma ou mais linhas
  "adsb:...". Nao ha reconexao a fazer (UDP nao tem conceito de
  conexao): se um datagrama se perde, o socket simplesmente segue
  esperando o proximo. Ver discussao TCP x UDP no README.
- replay_source(): le linhas de um arquivo (ex.: uma captura salva),
  para desenvolvimento e testes sem depender de uma fonte ao vivo.
- SerialLink / serial_source(): le linhas de uma porta serial (receptor da
  estacao de solo). SerialLink tambem permite ENVIAR bytes (ex.: o 'P' de
  ping para a CanSat) e reconecta sozinha se o USB for desconectado.
"""

import socket
import sys
import threading
import time
from typing import Callable, Iterator, Optional

try:  # pyserial so e' exigido de fato pela fonte --serial
    import serial
except ImportError:  # pragma: no cover
    serial = None

from .log import error, log, warn


def stdin_source() -> Iterator[str]:
    """Gera uma linha por vez a partir da entrada padrao."""
    for linha in sys.stdin:
        yield linha.rstrip("\n")


def tcp_source(
    host: str,
    port: int,
    reconectar_apos: float = 5.0,
    max_tentativas: Optional[int] = None,
) -> Iterator[str]:
    """Conecta como cliente TCP em host:port e gera uma linha por vez.

    Reconecta automaticamente em caso de queda de conexao, o que e'
    esperado dado que o enlace via satelite pode apresentar lacunas
    (CONTEXT.md 5). max_tentativas=None significa tentar
    indefinidamente.
    """
    tentativas = 0
    while max_tentativas is None or tentativas < max_tentativas:
        tentativas += 1
        try:
            log(f"Conectando na estacao de solo em {host}:{port}...")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((host, port))
                log("Conectado! Recebendo dados...")
                tentativas = 0  # reseta apos conexao bem-sucedida
                buffer = ""
                while True:
                    data = s.recv(4096)
                    if not data:
                        error("Conexao encerrada pelo servidor.")
                        break
                    buffer += data.decode("utf-8", errors="ignore")
                    while "\n" in buffer:
                        linha, buffer = buffer.split("\n", 1)
                        yield linha.rstrip("\r")
        except (OSError, ConnectionError) as e:
            error(f"Erro de conexao com a estacao de solo: {e}")

        warn(f"Tentando reconectar em {reconectar_apos:.0f}s...")
        time.sleep(reconectar_apos)


def udp_source(
    host: str,
    port: int,
    buffer_size: int = 65536,
) -> Iterator[str]:
    """Abre um socket UDP, faz bind em host:port e gera uma linha por vez.

    Diferenca fundamental em relacao a tcp_source(): aqui nao existe
    conexao. O visualizador so reserva o endereco local (bind) e fica
    esperando datagramas chegarem - quem inicia o envio e' sempre a
    estacao de solo, sem qualquer aperto de mao (handshake) previo e
    sem confirmacao de entrega (nem no nivel de transporte, nem
    nesta aplicacao).

    Cada datagrama recebido pode conter uma ou mais linhas separadas
    por "\\n" (para o caso de o remetente agrupar varias mensagens
    num so envio); linhas em branco dentro do datagrama sao ignoradas
    aqui e o parser trata qualquer conteudo malformado remanescente,
    exatamente como nas demais fontes (CONTEXT.md 2.2).

    Ao contrario de tcp_source(), uma falha aqui (ex.: porta ja em
    uso, sem permissao para o bind) e' um erro de configuracao, nao
    uma queda transitoria de enlace - por isso ela e' propagada
    (OSError) em vez de entrar num loop de retentativas.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((host, port))
        log(f"Ouvindo UDP em {host}:{port}...")
        while True:
            dados, origem = s.recvfrom(buffer_size)
            if not dados:
                continue
            texto = dados.decode("utf-8", errors="ignore")
            for linha in texto.splitlines():
                if linha:
                    yield linha


def replay_source(
    caminho: str,
    linhas_por_segundo: float = 5.0,
    repetir: bool = False,
) -> Iterator[str]:
    """Le linhas de um arquivo de captura, opcionalmente espacando a
    emissao para simular chegada ao vivo. linhas_por_segundo <= 0
    emite o arquivo inteiro o mais rapido possivel (sem pausas)."""
    intervalo = 1.0 / linhas_por_segundo if linhas_por_segundo > 0 else 0.0
    primeira_passada = True
    while repetir or primeira_passada:
        primeira_passada = False
        with open(caminho, "r", encoding="utf-8") as arquivo:
            for linha in arquivo:
                yield linha.rstrip("\n")
                if intervalo:
                    time.sleep(intervalo)
        if repetir:
            log(f"Fim do arquivo de replay ({caminho}), reiniciando (--replay-loop).")

class SerialLink:
    """Porta serial bidirecional: gera linhas recebidas e aceita envio.

    - linhas(): generator infinito de linhas (str, sem terminador). Se a
      porta nao abrir ou cair (ex.: USB desconectado), registra o erro e
      tenta reabrir a cada `reconectar_apos` segundos - igual a tcp_source.
    - enviar(dados): escreve bytes na porta; devolve False (sem levantar)
      se nao ha porta aberta no momento.

    `abrir` permite injetar uma fabrica de porta (usado nos testes, sem
    hardware); por padrao abre serial.Serial(porta, baud, timeout=1).
    """

    def __init__(
        self,
        porta: str,
        baud_rate: int = 115200,
        reconectar_apos: float = 3.0,
        espera_apos_abrir: float = 1.0,
        abrir: Optional[Callable[[], object]] = None,
    ) -> None:
        self.porta = porta
        self.baud_rate = baud_rate
        self._reconectar_apos = reconectar_apos
        self._espera_apos_abrir = espera_apos_abrir
        self._abrir = abrir or self._abrir_padrao
        self._ser = None
        self._lock = threading.Lock()

    def _abrir_padrao(self):
        if serial is None:
            raise OSError("pyserial nao instalado (pip install pyserial)")
        return serial.Serial(self.porta, self.baud_rate, timeout=1)

    @property
    def conectado(self) -> bool:
        with self._lock:
            return self._ser is not None

    def enviar(self, dados: bytes) -> bool:
        with self._lock:
            if self._ser is None:
                return False
            try:
                self._ser.write(dados)
                self._ser.flush()
                return True
            except (OSError, ValueError) as e:
                error(f"Falha ao escrever na serial: {e}")
                return False

    def linhas(self) -> Iterator[str]:
        while True:
            ser = None
            try:
                ser = self._abrir()
                # Placas Arduino/ESP reiniciam ao abrir a porta: espera e
                # descarta o lixo inicial (igual ao solo.py original).
                time.sleep(self._espera_apos_abrir)
                ser.reset_input_buffer()
                with self._lock:
                    self._ser = ser
                log(f"Conectado a {self.porta} a {self.baud_rate} baud. Aguardando dados...")

                while True:
                    bruto = ser.readline()  # bloqueia ate 1 s (timeout) - sem busy-loop
                    if not bruto:
                        continue
                    linha = bruto.decode("utf-8", errors="replace").strip()
                    if linha:
                        yield linha
            except OSError as e:  # serial.SerialException herda de OSError
                error(f"Erro na porta serial {self.porta}: {e}")
            finally:
                with self._lock:
                    self._ser = None
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass

            warn(f"Tentando reabrir {self.porta} em {self._reconectar_apos:.0f}s...")
            time.sleep(self._reconectar_apos)


def serial_source(porta: str, baud_rate: int = 115200) -> Iterator[str]:
    """Atalho compativel com a API anterior: so as linhas, sem envio."""
    return SerialLink(porta, baud_rate).linhas()
