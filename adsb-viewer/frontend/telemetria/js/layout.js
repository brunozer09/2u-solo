// layout.js — monta os painéis do dashboard a partir de layout.* do schema.
//
// O HTML mantém só o esqueleto (cabeçalho, painel 3D e os contêineres abaixo).
// Cada valor exibido é um elemento com data-field="<chave>" (e, opcionalmente,
// data-casas="N") que atualizarCampos() preenche a cada pacote.
//
//   #resumo           <- layout.resumo
//   #side-column      <- layout.paineis_laterais (depois do painel 3D)
//   #charts-grid      <- layout.graficos
//   #sensor-strip     <- layout.faixa_sensores
//
// O markup gerado é idêntico ao que existia escrito à mão, então o
// dashboard.css continua valendo sem mudanças.

import { buildCharts } from "./charts.js";
import { byId, formatarCampo } from "./format.js";

function criar(tag, classe, texto) {
    const elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto !== undefined) elemento.textContent = texto;
    return elemento;
}

function valor(chave, casas) {
    const elemento = criar("strong", "", "—");
    elemento.dataset.field = chave;
    if (casas !== undefined && casas !== null) elemento.dataset.casas = String(casas);
    return elemento;
}

function unidade(campo) {
    return campo?.unidade ? criar("small", "", campo.unidade) : null;
}

function avisarCampoDesconhecido(chave, onde) {
    console.warn(`Schema: ${onde} usa o campo desconhecido '${chave}'`);
}

// ---- cartões do topo --------------------------------------------------------

function criarResumo(container, schema) {
    for (const item of schema.layout.resumo ?? []) {
        const chave = typeof item === "string" ? item : item.campo;
        const casas = typeof item === "string" ? undefined : item.casas;
        const campo = schema.campos.get(chave);

        if (!campo) {
            avisarCampoDesconhecido(chave, "layout.resumo");
            continue;
        }

        const cartao = criar("article", "summary-card");
        const linha = criar("div");
        linha.append(valor(chave, casas));
        const un = unidade(campo);
        if (un) linha.append(un);
        cartao.append(criar("span", "", campo.rotulo_curto ?? campo.rotulo.toUpperCase()), linha);
        container.append(cartao);
    }
}

// ---- painéis laterais -------------------------------------------------------

const CLASSE_COLUNAS = { 1: "gps-values", 2: "two-columns", 3: "three-columns" };

function criarPainelLateral(painel, schema) {
    const secao = criar("section", "panel telemetry-panel");

    const cabecalho = criar("div", "panel-heading compact-heading");
    const titulos = criar("div");
    titulos.append(criar("span", "eyebrow", painel.eyebrow ?? ""), criar("h2", "", painel.titulo));
    cabecalho.append(titulos);

    if (painel.selo === "checksum") {
        const selo = criar("span", "checksum", "—");
        selo.id = "checksum-status";
        cabecalho.append(selo);
    }

    const colunas = painel.colunas ?? 2;
    const grade = criar("div", `data-grid ${CLASSE_COLUNAS[colunas] ?? "two-columns"}`);

    for (const chave of painel.campos) {
        const campo = schema.campos.get(chave);

        if (!campo) {
            avisarCampoDesconhecido(chave, `painel '${painel.titulo}'`);
            continue;
        }

        const celula = criar("div", colunas === 1 ? "data-cell wide-value" : "data-cell");
        celula.append(criar("span", "", campo.rotulo), valor(chave));
        const un = unidade(campo);
        if (un) celula.append(un);
        grade.append(celula);
    }

    secao.append(cabecalho, grade);
    return secao;
}

// ---- faixa de sensores ------------------------------------------------------

function criarFaixaSensores(container, schema) {
    const grupos = schema.layout.faixa_sensores ?? [];

    grupos.forEach((grupo, indice) => {
        if (indice > 0) container.append(criar("div", "sensor-divider"));

        const bloco = criar("div", "sensor-group");
        const valores = criar("div", "sensor-values");

        for (const chave of grupo.campos) {
            const campo = schema.campos.get(chave);

            if (!campo) {
                avisarCampoDesconhecido(chave, `faixa_sensores '${grupo.titulo}'`);
                continue;
            }

            const item = criar("div");
            item.append(criar("span", "", campo.rotulo), valor(chave));
            const un = unidade(campo);
            if (un) item.append(un);
            valores.append(item);
        }

        bloco.append(criar("span", "eyebrow", grupo.titulo), valores);
        container.append(bloco);
    });
}

// ---- entrada ----------------------------------------------------------------

/**
 * Gera todo o conteúdo dinâmico. Devolve { graficos, destaques, vinculos }:
 * `vinculos` é a lista de elementos [data-field] (inclusive os escritos à mão no
 * HTML, como GX/GY/GZ do painel 3D) já resolvidos contra o schema.
 */
export function renderizarLayout(schema) {
    const layout = schema.layout ?? {};
    schema.layout = layout;

    criarResumo(byId("resumo"), schema);

    const colunaLateral = byId("side-column");
    for (const painel of layout.paineis_laterais ?? []) {
        colunaLateral.append(criarPainelLateral(painel, schema));
    }

    const { graficos, destaques } = buildCharts(byId("charts-grid"), layout.graficos ?? []);

    criarFaixaSensores(byId("sensor-strip"), schema);

    const vinculos = [];
    for (const elemento of document.querySelectorAll("[data-field]")) {
        const campo = schema.campos.get(elemento.dataset.field);

        if (!campo) {
            avisarCampoDesconhecido(elemento.dataset.field, "o HTML");
            continue;
        }

        const casas = elemento.dataset.casas !== undefined
            ? Number(elemento.dataset.casas)
            : undefined;

        vinculos.push({ elemento, campo, casas });
    }

    return { graficos, destaques, vinculos };
}

/** Preenche todos os elementos [data-field] com os valores do pacote. */
export function atualizarCampos(vinculos, pacote) {
    for (const { elemento, campo, casas } of vinculos) {
        elemento.textContent = formatarCampo(campo, pacote[campo.chave], casas);
    }
}
