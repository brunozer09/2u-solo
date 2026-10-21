"""
telemetry_store.py

Guarda os ultimos pacotes de telemetria e distribui cada pacote novo para
os navegadores conectados (assinantes do stream SSE).

Por que uma fila por assinante (em vez de escrever direto no socket a
partir da thread de ingestao): um navegador lento ou travado nunca pode
atrasar a ingestao nem os demais clientes. Se a fila de um assinante
encher, o pacote MAIS ANTIGO dele e' descartado.

O historico limitado permite que um navegador que abre (ou recarrega) a
pagina no meio do voo receba os ultimos pacotes e reconstrua os graficos.
"""

import queue
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from .telemetry import PacoteTelemetria

# Item colocado nas filas para pedir que o assinante encerre.
ENCERRAR = object()


class TelemetryStore:
    def __init__(self, historico_max: int = 240, fila_max: int = 512) -> None:
        if historico_max < 1:
            raise ValueError("historico_max deve ser >= 1")
        self._historico: Deque[Dict[str, Any]] = deque(maxlen=historico_max)
        self._fila_max = fila_max
        self._assinantes: List["queue.Queue[Any]"] = []
        self._total = 0
        self._lock = threading.Lock()

    @property
    def total(self) -> int:
        with self._lock:
            return self._total

    @property
    def assinantes(self) -> int:
        with self._lock:
            return len(self._assinantes)

    def publicar(self, pacote: PacoteTelemetria) -> Dict[str, Any]:
        """Registra o pacote e o entrega a todos os assinantes.
        Devolve o registro (dict JSON-ready, com 'seq')."""
        with self._lock:
            self._total += 1
            registro = {**pacote.para_dict(), "seq": self._total}
            self._historico.append(registro)
            for fila in self._assinantes:
                self._entregar(fila, registro)
            return registro

    @staticmethod
    def _entregar(fila: "queue.Queue[Any]", item: Any) -> None:
        try:
            fila.put_nowait(item)
        except queue.Full:
            try:
                fila.get_nowait()  # descarta o mais antigo
            except queue.Empty:
                pass
            try:
                fila.put_nowait(item)
            except queue.Full:
                pass

    def assinar(self) -> Tuple["queue.Queue[Any]", List[Dict[str, Any]]]:
        """Cria uma fila de assinante e devolve (fila, historico_atual).
        Atomico: nenhum pacote se perde nem se repete entre o historico e a fila."""
        fila: "queue.Queue[Any]" = queue.Queue(maxsize=self._fila_max)
        with self._lock:
            backlog = list(self._historico)
            self._assinantes.append(fila)
        return fila, backlog

    def cancelar(self, fila: "queue.Queue[Any]") -> None:
        with self._lock:
            if fila in self._assinantes:
                self._assinantes.remove(fila)

    def ultimo(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._historico[-1] if self._historico else None

    def historico(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._historico)

    def idade_ultimo(self, agora: Optional[float] = None) -> Optional[float]:
        """Segundos desde o ultimo pacote (None se nunca chegou nenhum)."""
        ultimo = self.ultimo()
        if ultimo is None:
            return None
        agora = time.time() if agora is None else agora
        return max(0.0, agora - ultimo["t_pc"])

    def encerrar(self) -> None:
        """Pede a todos os assinantes que terminem (usado no shutdown)."""
        with self._lock:
            for fila in self._assinantes:
                self._entregar(fila, ENCERRAR)
