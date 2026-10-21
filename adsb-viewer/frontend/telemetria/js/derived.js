// derived.js — campos CALCULADOS no navegador (não vêm no pacote serial).
//
// Para criar um campo derivado novo:
//   1. declare-o em config/telemetry_schema.json com "derivado": true;
//   2. devolva o valor com a mesma chave em criarCalculadorDerivados().

import { finiteNumber } from "./format.js";

/** Taxa de pacotes (Hz) a partir da diferença entre `millis`, com média móvel. */
export class TaxaPacotes {
    constructor() {
        this.ultimoMillis = null;
        this.periodoMs = null;
    }

    atualizar(pacote) {
        const millis = finiteNumber(pacote.millis);

        if (millis === null) {
            return this.hz();
        }

        if (this.ultimoMillis !== null) {
            const delta = millis - this.ultimoMillis;

            if (delta > 0 && delta < 10000) {
                this.periodoMs = this.periodoMs === null
                    ? delta
                    : (this.periodoMs * 0.75) + (delta * 0.25);
            }
        }

        this.ultimoMillis = millis;

        return this.hz();
    }

    hz() {
        return this.periodoMs && this.periodoMs > 0
            ? 1000 / this.periodoMs
            : null;
    }
}

/** Devolve uma função `pacote -> pacote enriquecido` que mantém estado interno. */
export function criarCalculadorDerivados() {
    const taxa = new TaxaPacotes();

    return (pacote) => ({
        ...pacote,
        taxa_hz: taxa.atualizar(pacote)
    });
}
