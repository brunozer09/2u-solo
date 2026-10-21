// format.js — utilidades de DOM e formatação (sem estado, sem dependências).

export function byId(id) {
    return document.getElementById(id);
}

export function setText(id, value) {
    const element = byId(id);

    if (element) {
        element.textContent = value;
    }
}

/**
 * Converte para número finito ou devolve null.
 * Atenção: null/undefined/"" viram null (e não 0, como Number(null) faria),
 * porque o servidor envia `null` para campos ausentes do pacote.
 */
export function finiteNumber(value) {
    if (value === null || value === undefined || value === "") {
        return null;
    }

    const number = Number(value);

    return Number.isFinite(number)
        ? number
        : null;
}

export function formatNumber(value, decimals = 2) {
    const number = finiteNumber(value);

    return number === null
        ? "—"
        : number.toFixed(decimals);
}

export function formatInteger(value) {
    const number = finiteNumber(value);

    return number === null
        ? "—"
        : Math.round(number).toString();
}

/** millis desde o boot da CanSat -> "HH:MM:SS". */
export function formatMissionTime(value) {
    const millis = finiteNumber(value);

    if (millis === null || millis < 0) {
        return "00:00:00";
    }

    const totalSeconds = Math.floor(millis / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    return [hours, minutes, seconds]
        .map((part) => String(part).padStart(2, "0"))
        .join(":");
}

export function formatPcTime(value) {
    if (!value) {
        return "Recebido agora";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "Recebido agora";
    }

    return `Recebido ${date.toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
    })}`;
}

/**
 * Formata o valor de um campo conforme o schema.
 * `casas` (opcional) sobrescreve as casas decimais do campo. Campos sem casas
 * (ex.: id) são exibidos como vieram.
 */
export function formatarCampo(campo, valor, casas) {
    const decimais = casas ?? campo?.casas;

    if (decimais === undefined || decimais === null) {
        return valor === null || valor === undefined || valor === "" ? "—" : String(valor);
    }

    return formatNumber(valor, decimais);
}
