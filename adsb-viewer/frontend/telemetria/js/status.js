// status.js — indicador de conexão do cabeçalho.

import { byId, setText } from "./format.js";

/** modo: "server" | "active" | "error" | "" (classes CSS de #connection-dot). */
export function setConnection(modo, titulo, detalhe) {
    const ponto = byId("connection-dot");

    if (ponto) {
        ponto.classList.remove("server", "active", "error");

        if (modo) {
            ponto.classList.add(modo);
        }
    }

    setText("connection-text", titulo);
    setText("connection-detail", detalhe);
}
