// main.js — ponto de entrada do painel de telemetria.
//
//   SSE (/api/telemetry/stream) -> processarPacote():
//        derivados (taxa) -> campos [data-field] -> checksum -> atitude 3D -> gráficos
//
// Layout, campos e gráficos vêm do schema (config/telemetry_schema.json).

import { atualizarAtitude, criarAtitude } from "./attitude.js";
import { atualizarDestaques, atualizarGraficos } from "./charts.js";
import { criarCalculadorDerivados } from "./derived.js";
import { byId, formatMissionTime, formatPcTime, setText } from "./format.js";
import { atualizarCampos, renderizarLayout } from "./layout.js";
import { OrientationRenderer } from "./orientation3d.js";
import { carregarSchema } from "./schema.js";
import { setConnection } from "./status.js";
import { iniciarStream } from "./stream.js";

const MODELO_3D = "model.obj";
const SEM_PACOTE_APOS_MS = 3500;
const URL_PING = "/api/telemetry/ping";

const estado = {
    schema: null,
    vinculos: [],
    graficos: new Map(),
    destaques: new Map(),
    atitude: criarAtitude(),
    renderer: null,
    derivar: criarCalculadorDerivados(),
    ultimoPacoteEm: 0
};

// ------------------------------------------------------------
// Atualização por pacote
// ------------------------------------------------------------

function atualizarChecksum(pacote) {
    const elemento = byId("checksum-status");

    if (!elemento) {
        return;
    }

    const valido = Number(pacote.checksum) === 1;

    elemento.textContent = valido ? "CHECKSUM OK" : "CHECKSUM FALHOU";
    elemento.classList.toggle("ok", valido);
    elemento.classList.toggle("error", !valido);
}

function atualizarCabecalho(pacote) {
    setText("mission-time", formatMissionTime(pacote.millis));
    setText("packet-time", `ÚLTIMO PACOTE ${pacote.id ?? "—"}`);
}

/** `historico: true` reaplica pacotes antigos sem mexer no indicador de conexão. */
function processarPacote(bruto, { historico = false } = {}) {
    if (!bruto || typeof bruto !== "object") {
        return;
    }

    const pacote = estado.derivar(bruto);

    atualizarCampos(estado.vinculos, pacote);
    atualizarDestaques(estado.destaques, estado.schema, pacote);
    atualizarChecksum(pacote);
    atualizarCabecalho(pacote);

    if (atualizarAtitude(estado.atitude, pacote) && estado.renderer) {
        estado.renderer.setRotation(estado.atitude.roll, estado.atitude.pitch, estado.atitude.yaw);
    }

    atualizarGraficos(estado.graficos, pacote);

    if (!historico) {
        estado.ultimoPacoteEm = Date.now();
        setConnection("active", "Telemetria recebida", formatPcTime(pacote.t_pc_iso));
    }
}

// ------------------------------------------------------------
// PING (envia 'P' pela serial; só funciona com --serial)
// ------------------------------------------------------------

let temporizadorPing = null;

function mostrarStatusPing(texto, erro = false) {
    const elemento = byId("ping-status");

    if (!elemento) {
        return;
    }

    elemento.textContent = texto;
    elemento.classList.toggle("error", erro);
    clearTimeout(temporizadorPing);
    temporizadorPing = setTimeout(() => { elemento.textContent = ""; }, 3500);
}

async function enviarPing() {
    try {
        const resposta = await fetch(URL_PING, { method: "POST" });
        const corpo = await resposta.json().catch(() => ({}));

        if (resposta.ok && corpo.ok) {
            mostrarStatusPing("PING ENVIADO");
        } else {
            mostrarStatusPing(corpo.erro ?? `Falha (HTTP ${resposta.status})`, true);
        }
    } catch (erro) {
        mostrarStatusPing("Servidor indisponível", true);
    }
}

function configurarPing() {
    byId("ping-button")?.addEventListener("click", enviarPing);

    // Atalho: tecla P (igual ao `p` do terminal no solo.py original).
    document.addEventListener("keydown", (evento) => {
        const digitando = ["INPUT", "TEXTAREA", "SELECT"].includes(evento.target?.tagName);

        if (evento.key.toLowerCase() === "p" && !evento.repeat && !digitando
            && !evento.ctrlKey && !evento.metaKey && !evento.altKey) {
            enviarPing();
        }
    });
}

// ------------------------------------------------------------
// Inicialização
// ------------------------------------------------------------

function iniciarModelo3D() {
    const renderer = new OrientationRenderer(byId("glcanvas"));
    renderer.load(MODELO_3D);
    return renderer;
}

function vigiarSemPacote() {
    setInterval(() => {
        if (!estado.ultimoPacoteEm) {
            return;
        }

        const idade = Date.now() - estado.ultimoPacoteEm;

        if (idade > SEM_PACOTE_APOS_MS) {
            setConnection("server", "Servidor conectado", `Sem pacote há ${(idade / 1000).toFixed(1)} s`);
        }
    }, 500);
}

async function iniciar() {
    configurarPing();

    try {
        estado.schema = await carregarSchema();
    } catch (erro) {
        console.error("Não foi possível carregar o schema de telemetria:", erro);
        setConnection("error", "Telemetria indisponível", "Servidor sem telemetria (veja --no-telemetry)");
        return;
    }

    const { graficos, destaques, vinculos } = renderizarLayout(estado.schema);
    estado.graficos = graficos;
    estado.destaques = destaques;
    estado.vinculos = vinculos;
    estado.renderer = iniciarModelo3D();

    iniciarStream({
        aoAbrir: () => setConnection("server", "Servidor conectado", "Aguardando próximo pacote"),

        // Ao (re)conectar o servidor reenvia o histórico: reconstrói tudo do zero.
        aoBacklog: (pacotes, idadeUltimoS) => {
            estado.atitude = criarAtitude();
            estado.derivar = criarCalculadorDerivados();
            for (const grafico of estado.graficos.values()) {
                grafico.samples = [];
                grafico.draw();
            }

            pacotes.forEach((pacote) => processarPacote(pacote, { historico: true }));

            if (pacotes.length && idadeUltimoS !== null) {
                estado.ultimoPacoteEm = Date.now() - idadeUltimoS * 1000;
                setConnection("server", "Servidor conectado", `Histórico recuperado (${pacotes.length} pacotes)`);
            }
        },

        aoPacote: (pacote) => processarPacote(pacote),
        aoErro: () => setConnection("error", "Reconectando…", "Conexão SSE indisponível")
    });

    vigiarSemPacote();
}

// Disponível no console do navegador para testar sem hardware:
//   novoJsonRecebido({ millis: 1000, alt_baro: 120, ... })
//   rotacionar(roll, pitch, yaw)
window.novoJsonRecebido = processarPacote;
window.rotacionar = (x, y, z) => estado.renderer?.setRotation(Number(x) || 0, Number(y) || 0, Number(z) || 0);

iniciar();
