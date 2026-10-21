import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .parser import AtualizacaoAeronave


@dataclass
class EstadoAeronave:
    icao: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    air_speed: Optional[float] = None
    ultimo_timestamp: Optional[float] = None
    primeira_visao: float = field(default_factory=time.time)
    ultima_atualizacao: float = field(default_factory=time.time)
    num_atualizacoes: int = 0


class AircraftStore:
    """Store thread-safe indexado por icao.

    Dois limiares configuraveis, independentes um do outro:

    - stale_after: apos esse tempo (segundos) sem atualizacao, a
      aeronave e' marcada como "stale" (desatualizada). Ela continua
      aparecendo na tabela e no mapa (com destaque visual reduzido),
      conforme os criterios de aceite ("tabela mostra todas as
      aeronaves rastreadas, mesmo as expiradas recentemente").
    - remove_after: apos esse tempo, a aeronave e' removida do store
      por completo (some do mapa e da tabela). Use None para nunca
      remover automaticamente.
    """

    def __init__(
        self,
        stale_after: float = 30.0,
        remove_after: Optional[float] = 300.0,
    ) -> None:
        if remove_after is not None and remove_after < stale_after:
            raise ValueError(
                "remove_after deve ser >= stale_after "
                "(nao faz sentido remover antes de marcar como stale)"
            )
        self.stale_after = stale_after
        self.remove_after = remove_after
        self._aeronaves: Dict[str, EstadoAeronave] = {}
        self._lock = threading.Lock()

    def upsert(self, atualizacao: AtualizacaoAeronave, agora: Optional[float] = None) -> None:
        """Aplica uma atualizacao incremental de UMA aeronave.

        Campos ausentes (None) na atualizacao NAO sobrescrevem valores
        ja conhecidos - uma aeronave pode aparecer primeiro so com
        altitude/velocidade e ganhar posicao depois (CONTEXT.md 2.4).
        """
        agora = time.time() if agora is None else agora
        with self._lock:
            estado = self._aeronaves.get(atualizacao.icao)
            if estado is None:
                estado = EstadoAeronave(icao=atualizacao.icao, primeira_visao=agora)
                self._aeronaves[atualizacao.icao] = estado

            if atualizacao.latitude is not None:
                estado.latitude = atualizacao.latitude
            if atualizacao.longitude is not None:
                estado.longitude = atualizacao.longitude
            if atualizacao.altitude is not None:
                estado.altitude = atualizacao.altitude
            if atualizacao.air_speed is not None:
                estado.air_speed = atualizacao.air_speed
            if atualizacao.timestamp is not None:
                estado.ultimo_timestamp = atualizacao.timestamp

            estado.ultima_atualizacao = agora
            estado.num_atualizacoes += 1

    def _purgar_expiradas(self, agora: float) -> None:
        """Deve ser chamado com o lock ja adquirido."""
        if self.remove_after is None:
            return
        expiradas = [
            icao
            for icao, estado in self._aeronaves.items()
            if (agora - estado.ultima_atualizacao) > self.remove_after
        ]
        for icao in expiradas:
            del self._aeronaves[icao]

    def snapshot(self, agora: Optional[float] = None) -> List[dict]:
        """Retorna o estado atual de todas as aeronaves rastreadas
        (ja purgando as que passaram do remove_after), pronto para
        serializacao (ex.: JSON para a API)."""
        agora = time.time() if agora is None else agora
        with self._lock:
            self._purgar_expiradas(agora)
            resultado = []
            for estado in self._aeronaves.values():
                idade = agora - estado.ultima_atualizacao
                resultado.append(
                    {
                        "icao": estado.icao,
                        "latitude": estado.latitude,
                        "longitude": estado.longitude,
                        "altitude": estado.altitude,
                        "air_speed": estado.air_speed,
                        "ultima_atualizacao": estado.ultima_atualizacao,
                        "idade_segundos": idade,
                        "stale": idade > self.stale_after,
                        "num_atualizacoes": estado.num_atualizacoes,
                        "ultimo_timestamp": estado.ultimo_timestamp,
                    }
                )
            resultado.sort(key=lambda a: a["icao"])
            return resultado

    def __len__(self) -> int:
        with self._lock:
            return len(self._aeronaves)
