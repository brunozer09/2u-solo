"""
telemetry.py

Montagem e interpretacao dos pacotes de TELEMETRIA da CanSat que chegam
pelo mesmo fluxo de linhas das mensagens ADS-B (serial, tcp, udp, replay...).

Diferente da linha 'adsb:...' (uma linha = uma mensagem), um pacote de
telemetria ocupa VARIAS linhas, na ordem:

    Msg:rssi,snr,size
    Id:...
    Millis:...
    Bat:vbat,ibat
    Pos:lat,lon,alt_gps
    Baro:pressao,alt_baro,temp
    Acel:ax,ay,az
    Giro:gx,gy,gz
    Checksum:...

Os NOMES antes dos ':' sao ignorados; so a ORDEM dos valores importa e ela
e' definida pelo schema (config/telemetry_schema.json). O pacote comeca em
'Msg:' e termina em 'Checksum'.

MontadorPacote e' um automato de estados (nao faz I/O): recebe linha a
linha e diz (1) se a linha foi consumida como telemetria e (2) quando um
pacote ficou completo. Assim o roteamento telemetria x ADS-B fica no
laco de ingestao, sem as fontes saberem de nada disso.
"""

import math
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from .log import warn
from .parser import PREFIXO_ADSB, PREFIXOS_DE_LOG
from .telemetry_schema import SchemaTelemetria

CHAVE_INICIO = "msg"
CHAVE_FIM = "checksum"

# Protecao: um pacote real tem ~9 linhas. Se passar muito disso sem chegar
# em 'Checksum', algo se perdeu - descarta em vez de acumular lixo.
MAX_LINHAS_PACOTE = 32

# Linhas que o receptor imprime fora do pacote e que nunca sao telemetria.
LINHAS_DE_STATUS = ("RX", "TX", "ER")
_IGNORADAS_NO_PACOTE = PREFIXOS_DE_LOG + (PREFIXO_ADSB,)

_TOKENS_AUSENTES = ("", "nan", "none", "null")


@dataclass(frozen=True)
class PacoteTelemetria:
    """Um pacote completo ja interpretado."""

    campos: Dict[str, Any]       # chave do schema -> valor tipado (None = ausente)
    brutos: Tuple[str, ...]      # valores como recebidos, na ordem do schema (p/ CSV)
    recebido_em: float           # epoch (s) em que o pacote ficou completo
    completo: bool = True        # False se faltaram/sobraram valores

    @property
    def t_pc_iso(self) -> str:
        return datetime.fromtimestamp(self.recebido_em).isoformat()

    def para_dict(self) -> Dict[str, Any]:
        """Formato enviado ao navegador (JSON puro: sem NaN, None -> null)."""
        return {**self.campos, "t_pc": self.recebido_em, "t_pc_iso": self.t_pc_iso}


class ResultadoLinha(NamedTuple):
    consumida: bool                      # True: a linha pertence a um pacote de telemetria
    pacote: Optional[PacoteTelemetria]   # preenchido quando esta linha fechou um pacote


def separar_valores(texto: str) -> List[str]:
    """Separa os valores de uma linha: por virgula se houver, senao por espaco."""
    texto = texto.strip()
    if not texto:
        return []
    if "," in texto:
        return [parte.strip() for parte in texto.split(",")]
    return texto.split()


def converter_valor(bruto: str, tipo: str) -> Any:
    """Converte um valor textual para o tipo do schema.

    Ausente/ilegivel => None (nunca levanta excecao, nunca devolve NaN/inf,
    que nao existem em JSON valido).
    """
    texto = bruto.strip()
    if texto.lower() in _TOKENS_AUSENTES:
        return None
    if tipo == "texto":
        return texto
    try:
        numero = float(texto)
    except ValueError:
        return None
    if not math.isfinite(numero):
        return None
    if tipo == "int" and numero.is_integer():
        return int(numero)
    return numero


class MontadorPacote:
    def __init__(
        self,
        schema: SchemaTelemetria,
        relogio: Callable[[], float] = time.time,
    ) -> None:
        self._schema = schema
        self._relogio = relogio
        self._aberto = False
        self._valores: List[str] = []
        self._linhas = 0

    @property
    def em_andamento(self) -> bool:
        return self._aberto

    def _iniciar(self) -> None:
        self._aberto = True
        self._valores = []
        self._linhas = 0

    def descartar(self) -> None:
        self._aberto = False
        self._valores = []
        self._linhas = 0

    def alimentar(self, linha: str) -> ResultadoLinha:
        texto = linha.strip()
        chave = texto.split(":", 1)[0].strip().lower()

        # Inicio de pacote ('Msg:' obrigatoriamente com ':').
        if chave == CHAVE_INICIO and ":" in texto:
            if self._aberto:
                warn("Telemetria: novo 'Msg:' antes do 'Checksum', pacote anterior descartado")
            self._iniciar()
            self._linhas = 1
            self._valores.extend(separar_valores(texto.split(":", 1)[1]))
            return ResultadoLinha(True, None)

        # Fora de um pacote, nada aqui e' telemetria.
        if not self._aberto:
            return ResultadoLinha(False, None)

        # Dentro de um pacote:
        if not texto:
            return ResultadoLinha(True, None)
        if texto.startswith(_IGNORADAS_NO_PACOTE) or texto in LINHAS_DE_STATUS:
            # Linha de outro tipo intercalada: deixa o roteador trata-la; o pacote segue aberto.
            return ResultadoLinha(False, None)

        self._linhas += 1
        if self._linhas > MAX_LINHAS_PACOTE:
            warn(f"Telemetria: mais de {MAX_LINHAS_PACOTE} linhas sem 'Checksum', pacote descartado")
            self.descartar()
            return ResultadoLinha(False, None)

        conteudo = texto.split(":", 1)[1] if ":" in texto else texto
        self._valores.extend(separar_valores(conteudo))

        if chave == CHAVE_FIM:
            pacote = self._finalizar()
            self.descartar()
            return ResultadoLinha(True, pacote)
        return ResultadoLinha(True, None)

    def _finalizar(self) -> PacoteTelemetria:
        esperados = self._schema.campos_serial
        recebidos = len(self._valores)
        completo = recebidos == len(esperados)
        if not completo:
            warn(
                f"Telemetria: pacote com {recebidos} valor(es), esperado {len(esperados)} "
                "(confira config/telemetry_schema.json e o firmware)"
            )

        brutos = tuple(
            self._valores[i] if i < recebidos else "NaN" for i in range(len(esperados))
        )
        campos: Dict[str, Any] = {}
        for campo, bruto in zip(esperados, brutos):
            valor = converter_valor(bruto, campo.tipo)
            if valor is None and bruto.strip().lower() not in _TOKENS_AUSENTES:
                warn(f"Telemetria: valor invalido {bruto!r} no campo '{campo.chave}', tratado como ausente")
            campos[campo.chave] = valor

        return PacoteTelemetria(
            campos=campos,
            brutos=brutos,
            recebido_em=self._relogio(),
            completo=completo,
        )
