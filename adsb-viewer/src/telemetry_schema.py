"""
telemetry_schema.py

Contrato dos campos de telemetria da CanSat/CubeSat: UMA fonte da verdade
(config/telemetry_schema.json) lida tanto pelo backend (ordem dos valores
no pacote serial, tipos, cabecalho do CSV) quanto pelo front-end (rotulos,
unidades, casas decimais, paineis e graficos - servido em
GET /api/telemetry/schema).

Para adicionar/alterar um dado exibido, edite o JSON; nao ha mais lista de
campos duplicada em Python e JavaScript.

Regras do JSON (validadas em carregar_schema; erro => ValueError claro):

- "campos": lista ORDENADA. Os campos nao-derivados correspondem, na mesma
  ordem, aos valores do pacote serial (Msg ... Checksum). Campos com
  "derivado": true sao calculados no navegador (ex.: taxa_hz) e nao
  existem no pacote serial.
- "tipo": "float" (padrao), "int" ou "texto".
- "layout" so pode referenciar chaves declaradas em "campos".
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

CAMINHO_PADRAO = Path(__file__).resolve().parent.parent / "config" / "telemetry_schema.json"

TIPOS_VALIDOS = ("float", "int", "texto")

# Chaves que o servidor acrescenta a cada pacote: um campo do schema
# nao pode usa-las.
CHAVES_RESERVADAS = ("t_pc", "t_pc_iso", "seq")

_PADRAO_CHAVE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class CampoTelemetria:
    chave: str
    rotulo: str
    unidade: str = ""
    casas: Optional[int] = None
    tipo: str = "float"
    derivado: bool = False


class SchemaTelemetria:
    """Schema validado. Imutavel depois de criado."""

    def __init__(self, dados: Dict[str, Any]) -> None:
        if not isinstance(dados, dict):
            raise ValueError("schema de telemetria: o JSON deve ser um objeto")
        self._dados = dados
        self.campos: Tuple[CampoTelemetria, ...] = self._ler_campos(dados.get("campos"))
        self._por_chave = {c.chave: c for c in self.campos}
        self._validar_layout(dados.get("layout", {}))

        self.campos_serial: Tuple[CampoTelemetria, ...] = tuple(
            c for c in self.campos if not c.derivado
        )
        if not self.campos_serial:
            raise ValueError("schema de telemetria: nenhum campo vindo da serial")
        self.chaves_serial: Tuple[str, ...] = tuple(c.chave for c in self.campos_serial)

    # ------------------------------------------------------------------
    # validacao
    # ------------------------------------------------------------------

    @staticmethod
    def _ler_campos(bruto: Any) -> Tuple[CampoTelemetria, ...]:
        if not isinstance(bruto, list) or not bruto:
            raise ValueError("schema de telemetria: 'campos' deve ser uma lista nao vazia")

        campos = []
        vistas = set()
        for i, item in enumerate(bruto):
            if not isinstance(item, dict):
                raise ValueError(f"schema de telemetria: campos[{i}] deve ser um objeto")

            chave = item.get("chave")
            if not isinstance(chave, str) or not _PADRAO_CHAVE.match(chave):
                raise ValueError(
                    f"schema de telemetria: campos[{i}].chave invalida {chave!r} "
                    "(use minusculas, digitos e '_', comecando por letra)"
                )
            if chave in CHAVES_RESERVADAS:
                raise ValueError(f"schema de telemetria: a chave '{chave}' e' reservada")
            if chave in vistas:
                raise ValueError(f"schema de telemetria: chave duplicada '{chave}'")
            vistas.add(chave)

            tipo = item.get("tipo", "float")
            if tipo not in TIPOS_VALIDOS:
                raise ValueError(
                    f"schema de telemetria: campo '{chave}' com tipo invalido {tipo!r} "
                    f"(validos: {', '.join(TIPOS_VALIDOS)})"
                )

            casas = item.get("casas")
            if casas is not None and (
                not isinstance(casas, int) or isinstance(casas, bool) or casas < 0
            ):
                raise ValueError(
                    f"schema de telemetria: campo '{chave}' com 'casas' invalido {casas!r}"
                )

            campos.append(
                CampoTelemetria(
                    chave=chave,
                    rotulo=str(item.get("rotulo", chave)),
                    unidade=str(item.get("unidade", "")),
                    casas=casas,
                    tipo=tipo,
                    derivado=bool(item.get("derivado", False)),
                )
            )
        return tuple(campos)

    def _exigir(self, chave: Any, onde: str) -> None:
        if chave not in self._por_chave:
            raise ValueError(
                f"schema de telemetria: {onde} referencia o campo inexistente {chave!r}"
            )

    def _validar_layout(self, layout: Any) -> None:
        if not isinstance(layout, dict):
            raise ValueError("schema de telemetria: 'layout' deve ser um objeto")

        for i, item in enumerate(layout.get("resumo", [])):
            chave = item.get("campo") if isinstance(item, dict) else item
            self._exigir(chave, f"layout.resumo[{i}]")

        for secao in ("paineis_laterais", "faixa_sensores"):
            for i, painel in enumerate(layout.get(secao, [])):
                for chave in painel.get("campos", []):
                    self._exigir(chave, f"layout.{secao}[{i}]")

        ids_graficos = set()
        for i, grafico in enumerate(layout.get("graficos", [])):
            gid = grafico.get("id")
            if not isinstance(gid, str) or not re.match(r"^[a-z][a-z0-9_-]*$", gid or ""):
                raise ValueError(f"schema de telemetria: layout.graficos[{i}].id invalido {gid!r}")
            if gid in ids_graficos:
                raise ValueError(f"schema de telemetria: id de grafico duplicado '{gid}'")
            ids_graficos.add(gid)

            series = grafico.get("series", [])
            if not series:
                raise ValueError(f"schema de telemetria: grafico '{gid}' sem series")
            for serie in series:
                self._exigir(serie.get("chave"), f"layout.graficos['{gid}'].series")
            for chave in grafico.get("destaque", []):
                self._exigir(chave, f"layout.graficos['{gid}'].destaque")

    # ------------------------------------------------------------------
    # acesso
    # ------------------------------------------------------------------

    def campo(self, chave: str) -> CampoTelemetria:
        return self._por_chave[chave]

    def para_dict(self) -> Dict[str, Any]:
        """Dicionario pronto para JSON (e' o proprio arquivo, ja validado)."""
        return self._dados


def carregar_schema(caminho: Optional[Path] = None) -> SchemaTelemetria:
    caminho = Path(caminho) if caminho is not None else CAMINHO_PADRAO
    try:
        texto = caminho.read_text(encoding="utf-8")
    except OSError as erro:
        raise ValueError(f"nao foi possivel ler o schema de telemetria '{caminho}': {erro}") from erro
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise ValueError(f"JSON invalido em '{caminho}': {erro}") from erro
    return SchemaTelemetria(dados)
