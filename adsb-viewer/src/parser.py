from dataclasses import dataclass
from typing import Optional

from .log import warn, debug

PREFIXO_ADSB = "adsb:"
NUM_CAMPOS_ESPERADOS = 5

PREFIXOS_DE_LOG = ("[LOG]", "[WARN]", "[ERROR]", "[DEBUG]")

@dataclass(frozen=True)
class AtualizacaoAeronave:
    icao: str
    latitude: Optional[float]
    longitude: Optional[float]
    altitude: Optional[float]
    air_speed: Optional[float]
    raw: str


def _parse_float_opcional(campo: str) -> Optional[float]:
    """Converte um campo em float, tratando o token literal "None"
    (e string vazia) como valor ausente."""
    valor = campo.strip()
    if valor == "" or valor.lower() == "none":
        return None
    try:
        return float(valor)
    except ValueError:
        warn(f"Valor numerico invalido '{campo}', tratado como ausente")
        return None


def parse_line(linha: str) -> Optional[AtualizacaoAeronave]:
    """Faz o parsing de uma linha recebida da estacao de solo.

    Retorna None (e loga o motivo) para qualquer linha que nao siga o
    contrato `adsb:icao,lat,lon,alt,air_speed` - incluindo linhas de
    log do payload e linhas malformadas. Nunca lanca excecao para uma
    linha invalida: o chamador pode simplesmente ignorar o retorno
    None e seguir para a proxima linha.
    """
    linha_original = linha
    linha = linha.strip()

    if not linha:
        return None

    if linha.startswith(PREFIXOS_DE_LOG):
        debug(f"Linha de log do payload ignorada: {linha}")
        return None

    if not linha.startswith(PREFIXO_ADSB):
        warn(f"Linha fora do formato esperado, ignorada: {linha_original!r}")
        return None

    corpo = linha[len(PREFIXO_ADSB):]
    campos = corpo.split(",")

    if len(campos) != NUM_CAMPOS_ESPERADOS:
        warn(
            f"Linha 'adsb:' com {len(campos)} campo(s) "
            f"(esperado {NUM_CAMPOS_ESPERADOS}), ignorada: {linha_original!r}"
        )
        return None

    icao_bruto, lat_bruta, lon_bruta, alt_bruta, spd_bruta = campos
    icao = icao_bruto.strip()

    if not icao or icao.lower() == "none":
        warn(f"Linha 'adsb:' sem icao valido, ignorada: {linha_original!r}")
        return None

    return AtualizacaoAeronave(
        icao=icao,
        latitude=_parse_float_opcional(lat_bruta),
        longitude=_parse_float_opcional(lon_bruta),
        altitude=_parse_float_opcional(alt_bruta),
        air_speed=_parse_float_opcional(spd_bruta),
        raw=linha_original,
    )
