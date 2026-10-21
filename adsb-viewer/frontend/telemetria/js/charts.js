// charts.js — gráficos 2D em <canvas> puro, sem biblioteca externa.
//
// A classe TelemetryChart e a formatAxisValue vêm do dashboard original sem
// alteração de lógica; só foram trocadas as referências ao CONFIG global pelas
// constantes locais abaixo. buildCharts() (no fim do arquivo) cria os cards a
// partir de layout.graficos do schema, então um gráfico novo é só uma entrada
// no JSON.

import { byId, finiteNumber, formatNumber } from "./format.js";

const PADDING = Object.freeze({ top: 10, right: 10, bottom: 24, left: 46 });
const AMOSTRAS_PADRAO = 120;

export const CORES = Object.freeze({
    amber: "#f2aa36",
    red: "#ff7474",
    green: "#65d69a",
    cyan: "#62cbea",
    violet: "#b897ff"
});

export class TelemetryChart {

    constructor(canvasId, series, options = {}) {
        this.canvas =
            byId(canvasId);

        this.ctx =
            this.canvas?.getContext("2d") || null;

        this.series =
            series;

        this.samples =
            [];

        this.maxSamples =
            options.maxSamples ||
            AMOSTRAS_PADRAO;

        this.unit =
            options.unit || "";

        this.fixedRange =
            options.fixedRange || null;

        this.lastSize = {
            width: 0,
            height: 0,
            dpr: 0
        };

        if (!this.canvas || !this.ctx) {
            return;
        }

        if ("ResizeObserver" in window) {
            this.resizeObserver =
                new ResizeObserver(() => {
                    this.draw();
                });

            this.resizeObserver.observe(
                this.canvas
            );
        } else {
            window.addEventListener(
                "resize",
                () => this.draw()
            );
        }

        this.draw();
    }

    push(timeSeconds, packet) {
        if (
            !this.ctx ||
            !Number.isFinite(timeSeconds)
        ) {
            return;
        }

        const values = {};
        let hasValue = false;

        for (const item of this.series) {
            const value =
                finiteNumber(
                    packet[item.key]
                );

            values[item.key] =
                value;

            if (value !== null) {
                hasValue = true;
            }
        }

        if (!hasValue) {
            return;
        }

        this.samples.push({
            t: timeSeconds,
            values
        });

        if (
            this.samples.length >
            this.maxSamples
        ) {
            this.samples.splice(
                0,
                this.samples.length -
                this.maxSamples
            );
        }

        this.draw();
    }

    resizeCanvas() {
        const rect =
            this.canvas.getBoundingClientRect();

        const dpr =
            Math.min(
                window.devicePixelRatio || 1,
                2
            );

        const width =
            Math.max(
                1,
                Math.round(rect.width)
            );

        const height =
            Math.max(
                1,
                Math.round(rect.height)
            );

        if (
            this.lastSize.width !== width ||
            this.lastSize.height !== height ||
            this.lastSize.dpr !== dpr
        ) {
            this.canvas.width =
                Math.round(width * dpr);

            this.canvas.height =
                Math.round(height * dpr);

            this.lastSize = {
                width,
                height,
                dpr
            };
        }

        this.ctx.setTransform(
            dpr,
            0,
            0,
            dpr,
            0,
            0
        );

        return {
            width,
            height
        };
    }

    getRange() {
        if (this.fixedRange) {
            return this.fixedRange;
        }

        const values = [];

        for (const sample of this.samples) {
            for (const item of this.series) {
                const value =
                    sample.values[item.key];

                if (value !== null) {
                    values.push(value);
                }
            }
        }

        if (!values.length) {
            return {
                min: -1,
                max: 1
            };
        }

        let min =
            Math.min(...values);

        let max =
            Math.max(...values);

        if (min === max) {
            const delta =
                Math.max(
                    Math.abs(min) * 0.08,
                    1
                );

            min -= delta;
            max += delta;
        } else {
            const padding =
                (max - min) * 0.12;

            min -= padding;
            max += padding;
        }

        return {
            min,
            max
        };
    }

    drawGrid(
        ctx,
        plot,
        minY,
        maxY,
        minX,
        maxX
    ) {
        ctx.save();

        ctx.lineWidth = 1;

        ctx.font =
            "9px ui-sans-serif, system-ui, sans-serif";

        ctx.textBaseline =
            "middle";

        ctx.fillStyle =
            "rgba(146,154,161,0.82)";

        ctx.strokeStyle =
            "rgba(110,118,124,0.16)";

        const yLines = 4;

        for (
            let i = 0;
            i <= yLines;
            i++
        ) {
            const ratio =
                i / yLines;

            const y =
                plot.top +
                plot.height * ratio;

            const value =
                maxY -
                (maxY - minY) *
                ratio;

            ctx.beginPath();

            ctx.moveTo(
                plot.left,
                y
            );

            ctx.lineTo(
                plot.left +
                plot.width,
                y
            );

            ctx.stroke();

            ctx.textAlign =
                "right";

            ctx.fillText(
                formatAxisValue(value),
                plot.left - 7,
                y
            );
        }

        const xLines = 4;

        ctx.textBaseline =
            "top";

        for (
            let i = 0;
            i <= xLines;
            i++
        ) {
            const ratio =
                i / xLines;

            const x =
                plot.left +
                plot.width * ratio;

            const value =
                minX +
                (maxX - minX) *
                ratio;

            ctx.beginPath();

            ctx.moveTo(
                x,
                plot.top
            );

            ctx.lineTo(
                x,
                plot.top +
                plot.height
            );

            ctx.stroke();

            if (i === 0) {
                ctx.textAlign = "left";
            } else if (i === xLines) {
                ctx.textAlign = "right";
            } else {
                ctx.textAlign = "center";
            }

            ctx.fillText(
                `${value.toFixed(0)}s`,
                x,
                plot.top +
                plot.height +
                7
            );
        }

        ctx.restore();
    }

    drawEmpty(
        ctx,
        width,
        height
    ) {
        ctx.save();

        ctx.fillStyle =
            "rgba(146,154,161,0.62)";

        ctx.font =
            "10px ui-sans-serif, system-ui, sans-serif";

        ctx.textAlign =
            "center";

        ctx.textBaseline =
            "middle";

        ctx.fillText(
            "Aguardando amostras de telemetria",
            width / 2,
            height / 2
        );

        ctx.restore();
    }

    draw() {
        if (!this.ctx) {
            return;
        }

        const {
            width,
            height
        } = this.resizeCanvas();

        const ctx =
            this.ctx;

        ctx.clearRect(
            0,
            0,
            width,
            height
        );

        if (
            this.samples.length < 1
        ) {
            this.drawEmpty(
                ctx,
                width,
                height
            );

            return;
        }

        const padding =
            PADDING;

        const plot = {
            left:
                padding.left,

            top:
                padding.top,

            width:
                Math.max(
                    1,
                    width -
                    padding.left -
                    padding.right
                ),

            height:
                Math.max(
                    1,
                    height -
                    padding.top -
                    padding.bottom
                )
        };

        const {
            min,
            max
        } = this.getRange();

        let minX =
            this.samples[0].t;

        let maxX =
            this.samples[
                this.samples.length - 1
            ].t;

        if (minX === maxX) {
            maxX = minX + 1;
        }

        this.drawGrid(
            ctx,
            plot,
            min,
            max,
            minX,
            maxX
        );

        const xToCanvas =
            (x) =>
                plot.left +
                (
                    (x - minX) /
                    (maxX - minX)
                ) *
                plot.width;

        const yToCanvas =
            (y) =>
                plot.top +
                (
                    1 -
                    (y - min) /
                    (max - min)
                ) *
                plot.height;

        ctx.save();

        ctx.beginPath();

        ctx.rect(
            plot.left,
            plot.top,
            plot.width,
            plot.height
        );

        ctx.clip();

        for (
            const item of
            this.series
        ) {
            const points =
                this.samples
                    .map(
                        (sample) => ({
                            t: sample.t,
                            value:
                                sample.values[
                                    item.key
                                ]
                        })
                    )
                    .filter(
                        (point) =>
                            point.value !== null
                    );

            if (!points.length) {
                continue;
            }

            if (
                item.fill &&
                points.length > 1
            ) {
                const gradient =
                    ctx.createLinearGradient(
                        0,
                        plot.top,
                        0,
                        plot.top +
                        plot.height
                    );

                gradient.addColorStop(
                    0,
                    `${item.color}26`
                );

                gradient.addColorStop(
                    1,
                    `${item.color}00`
                );

                ctx.beginPath();

                ctx.moveTo(
                    xToCanvas(
                        points[0].t
                    ),
                    plot.top +
                    plot.height
                );

                for (
                    const point of
                    points
                ) {
                    ctx.lineTo(
                        xToCanvas(
                            point.t
                        ),
                        yToCanvas(
                            point.value
                        )
                    );
                }

                ctx.lineTo(
                    xToCanvas(
                        points[
                            points.length - 1
                        ].t
                    ),
                    plot.top +
                    plot.height
                );

                ctx.closePath();

                ctx.fillStyle =
                    gradient;

                ctx.fill();
            }

            ctx.beginPath();

            points.forEach(
                (point, index) => {
                    const x =
                        xToCanvas(
                            point.t
                        );

                    const y =
                        yToCanvas(
                            point.value
                        );

                    if (index === 0) {
                        ctx.moveTo(x, y);
                    } else {
                        ctx.lineTo(x, y);
                    }
                }
            );

            ctx.strokeStyle =
                item.color;

            ctx.lineWidth =
                item.width || 1.7;

            ctx.lineJoin =
                "round";

            ctx.lineCap =
                "round";

            ctx.stroke();

            const last =
                points[
                    points.length - 1
                ];

            ctx.beginPath();

            ctx.arc(
                xToCanvas(last.t),
                yToCanvas(last.value),
                2.5,
                0,
                Math.PI * 2
            );

            ctx.fillStyle =
                item.color;

            ctx.fill();
        }

        ctx.restore();
    }
}

function formatAxisValue(value) {
    const absolute =
        Math.abs(value);

    if (absolute >= 1000) {
        return value.toFixed(0);
    }

    if (absolute >= 100) {
        return value.toFixed(0);
    }

    if (absolute >= 10) {
        return value.toFixed(1);
    }

    return value.toFixed(2);
}


// ============================================================
// CONSTRUÇÃO A PARTIR DO SCHEMA
// ============================================================

function criar(tag, classe, texto) {
    const elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto !== undefined) elemento.textContent = texto;
    return elemento;
}

/**
 * Cria um card por entrada de `definicoes` (layout.graficos) dentro de
 * `container` e devolve { graficos: Map(id -> TelemetryChart),
 * destaques: Map(id -> { elemento, chaves }) }.
 */
export function buildCharts(container, definicoes) {
    const graficos = new Map();
    const destaques = new Map();

    for (const def of definicoes) {
        const card = criar("article", "panel chart-card");

        const cabecalho = criar("div", "chart-heading");
        const titulos = criar("div");
        titulos.append(criar("span", "eyebrow", def.eyebrow ?? ""), criar("h3", "", def.titulo ?? def.id));
        const destaque = criar("strong", "", "—");
        destaque.id = `chart-${def.id}-last`;
        cabecalho.append(titulos, destaque);

        const legenda = criar("div", "legend");
        for (const serie of def.series) {
            const item = criar("span");
            item.append(criar("i", `legend-line ${serie.cor ?? "amber"}`), document.createTextNode(serie.rotulo ?? serie.chave));
            legenda.append(item);
        }

        const tela = criar("canvas", "telemetry-chart");
        tela.id = `chart-${def.id}`;

        card.append(cabecalho, legenda, tela);
        container.append(card);

        graficos.set(
            def.id,
            new TelemetryChart(
                tela.id,
                def.series.map((s) => ({
                    key: s.chave,
                    color: CORES[s.cor] ?? CORES.amber,
                    fill: Boolean(s.preencher)
                })),
                {
                    maxSamples: def.amostras,
                    fixedRange: def.faixa_fixa ?? null
                }
            )
        );
        destaques.set(def.id, { elemento: destaque, chaves: def.destaque ?? [] });
    }

    return { graficos, destaques };
}

/** Envia o pacote a todos os gráficos (eixo X = tempo de missão em segundos). */
export function atualizarGraficos(graficos, pacote) {
    const millis = finiteNumber(pacote.millis);
    if (millis === null) return;
    for (const grafico of graficos.values()) {
        grafico.push(millis / 1000, pacote);
    }
}

/** Texto do canto do card: valor(es) de `destaque` + unidade do primeiro campo. */
export function atualizarDestaques(destaques, schema, pacote) {
    for (const { elemento, chaves } of destaques.values()) {
        if (!chaves.length) continue;
        const valores = chaves.map((chave) => {
            const campo = schema.campos.get(chave);
            return formatNumber(pacote[chave], campo?.casas ?? 2);
        });
        const unidade = schema.campos.get(chaves[0])?.unidade ?? "";
        elemento.textContent = unidade ? `${valores.join(" / ")} ${unidade}` : valores.join(" / ");
    }
}
