"""
telemetry_pipeline.py

Liga as pecas da telemetria para o laco de ingestao:

    linha -> MontadorPacote -> (pacote completo) -> TelemetryStore (SSE/historico)
                                                 -> RegistroCsvTelemetria (disco)

O laco de ingestao (main.ingest_loop) so precisa perguntar
`processar_linha(linha)`: se devolver True a linha era telemetria e nao
deve ir para o parser ADS-B.
"""

from typing import Optional

from .csv_log import RegistroCsvTelemetria
from .log import log
from .telemetry import MontadorPacote
from .telemetry_schema import SchemaTelemetria
from .telemetry_store import TelemetryStore


class ProcessadorTelemetria:
    def __init__(
        self,
        schema: SchemaTelemetria,
        store: TelemetryStore,
        csv_log: Optional[RegistroCsvTelemetria] = None,
        imprimir_pacotes: bool = True,
    ) -> None:
        self.schema = schema
        self.store = store
        self.csv_log = csv_log
        self._montador = MontadorPacote(schema)
        self._imprimir = imprimir_pacotes

    def processar_linha(self, linha: str) -> bool:
        """True se a linha foi consumida como parte de um pacote de telemetria."""
        resultado = self._montador.alimentar(linha)
        if resultado.pacote is not None:
            self._concluir(resultado.pacote)
        return resultado.consumida

    def _concluir(self, pacote) -> None:
        registro = self.store.publicar(pacote)
        if self.csv_log is not None:
            self.csv_log.registrar(pacote.brutos, pacote.t_pc_iso)
        if self._imprimir:
            log("TLM " + " | ".join(f"{k}={registro[k]}" for k in self.schema.chaves_serial))
