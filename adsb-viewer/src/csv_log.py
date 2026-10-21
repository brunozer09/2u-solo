"""
csv_log.py

Gravacao da telemetria em CSV, um arquivo por execucao
(launches/telemetria1.csv, telemetria2.csv, ...), sem nunca sobrescrever
um lancamento anterior.

Diferente da versao original (que reescrevia o arquivo INTEIRO a cada
pacote), aqui cada pacote e' ANEXADO e descarregado (flush) em seguida:
custo constante por pacote e, se o programa travar, tudo o que ja chegou
esta no disco. O arquivo so e' criado quando chega o primeiro pacote, entao
rodar so para ver ADS-B nao deixa CSVs vazios para tras.

Um erro de disco (cheio, sem permissao...) NUNCA derruba a ingestao: e'
registrado uma vez e a gravacao tenta de novo no pacote seguinte.
"""

import csv
import threading
from pathlib import Path
from typing import IO, Optional, Sequence

from .log import error, log

SEPARADOR_PADRAO = ";"


def proximo_arquivo_csv(diretorio: Path, prefixo: str = "telemetria") -> Path:
    """Primeiro nome livre 'prefixoN.csv' (N = maior indice existente + 1)."""
    diretorio.mkdir(parents=True, exist_ok=True)
    maior = 0
    for caminho in diretorio.iterdir():
        if not caminho.is_file() or caminho.suffix.lower() != ".csv":
            continue
        nome = caminho.stem.lower()
        if not nome.startswith(prefixo):
            continue
        sufixo = nome[len(prefixo):]
        if sufixo.isdigit():
            maior = max(maior, int(sufixo))
    return diretorio / f"{prefixo}{maior + 1}.csv"


class RegistroCsvTelemetria:
    def __init__(
        self,
        diretorio: Path,
        cabecalho: Sequence[str],
        separador: str = SEPARADOR_PADRAO,
        prefixo: str = "telemetria",
    ) -> None:
        self._diretorio = Path(diretorio)
        self._cabecalho = list(cabecalho)
        self._separador = separador
        self._prefixo = prefixo
        self._arquivo: Optional[IO[str]] = None
        self._escritor = None
        self._caminho: Optional[Path] = None
        self._falhou = False
        self._lock = threading.Lock()

    @property
    def caminho(self) -> Optional[Path]:
        """Arquivo em uso (None ate o primeiro pacote)."""
        return self._caminho

    def _abrir(self) -> None:
        # Modo 'x': falha se o arquivo ja existir (nunca sobrescreve);
        # nesse caso recalcula o proximo indice.
        for _ in range(100):
            caminho = proximo_arquivo_csv(self._diretorio, self._prefixo)
            try:
                arquivo = open(caminho, "x", newline="", encoding="utf-8")
            except FileExistsError:
                continue
            break
        else:
            raise OSError("nao foi possivel escolher um nome livre para o CSV")

        try:
            escritor = csv.writer(arquivo, delimiter=self._separador, lineterminator="\n")
            escritor.writerow(self._cabecalho)
            arquivo.flush()
        except OSError:
            arquivo.close()
            raise

        self._arquivo = arquivo
        self._escritor = escritor
        self._caminho = caminho
        log(f"CSV de telemetria: {caminho}")

    def registrar(self, valores: Sequence[str], t_pc_iso: str) -> bool:
        """Anexa uma linha. Devolve False (sem levantar) se o disco falhou."""
        linha = list(valores) + [t_pc_iso]
        with self._lock:
            try:
                if self._arquivo is None:
                    self._abrir()
                self._escritor.writerow(linha)
                self._arquivo.flush()
                self._falhou = False
                return True
            except OSError as erro:
                if not self._falhou:
                    error(f"Falha ao gravar o CSV de telemetria: {erro}")
                self._falhou = True
                return False

    def fechar(self) -> None:
        with self._lock:
            if self._arquivo is not None:
                try:
                    self._arquivo.close()
                except OSError:
                    pass
                self._arquivo = None
                self._escritor = None
