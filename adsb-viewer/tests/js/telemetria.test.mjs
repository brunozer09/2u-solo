// Testes dos módulos puros do painel de telemetria (sem navegador e sem dependências).
// Rodar com:  node --test tests/js/*.test.mjs   (na pasta adsb_viewer)

import assert from "node:assert/strict";
import { test } from "node:test";

import { atualizarAtitude, criarAtitude, wrapDegrees } from "../../frontend/telemetria/js/attitude.js";
import { TaxaPacotes, criarCalculadorDerivados } from "../../frontend/telemetria/js/derived.js";
import { finiteNumber, formatMissionTime, formatNumber, formatarCampo } from "../../frontend/telemetria/js/format.js";

const perto = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

test("finiteNumber: null/ausente NÃO vira 0", () => {
    assert.equal(finiteNumber(null), null);
    assert.equal(finiteNumber(undefined), null);
    assert.equal(finiteNumber(""), null);
    assert.equal(finiteNumber("abc"), null);
    assert.equal(finiteNumber(NaN), null);
    assert.equal(finiteNumber("12.5"), 12.5);
    assert.equal(finiteNumber(0), 0);
});

test("formatação: ausente vira traço, casas do schema são respeitadas", () => {
    assert.equal(formatNumber(null), "—");
    assert.equal(formatNumber(1.005, 1), "1.0");
    assert.equal(formatarCampo({ casas: 2 }, 7.4137), "7.41");
    assert.equal(formatarCampo({ casas: 2 }, 7.4137, 0), "7");   // data-casas sobrescreve
    assert.equal(formatarCampo({}, "A3"), "A3");                  // sem casas: como veio (id)
    assert.equal(formatarCampo({}, null), "—");
    assert.equal(formatarCampo({ casas: 1 }, null), "—");
});

test("tempo de missão", () => {
    assert.equal(formatMissionTime(null), "00:00:00");
    assert.equal(formatMissionTime(3_725_000), "01:02:05");
    assert.equal(formatMissionTime(-5), "00:00:00");
});

test("taxa de pacotes: 1 pacote/s => ~1 Hz; ignora saltos e repetidos", () => {
    const taxa = new TaxaPacotes();
    assert.equal(taxa.atualizar({ millis: 1000 }), null);          // precisa de 2 pacotes
    perto(taxa.atualizar({ millis: 2000 }), 1);
    perto(taxa.atualizar({ millis: 3000 }), 1);
    const antes = taxa.atualizar({ millis: 3000 });                // delta 0: ignorado
    perto(antes, 1);
    perto(taxa.atualizar({ millis: 60000 }), 1);                   // salto > 10 s: ignorado
    assert.equal(taxa.atualizar({ millis: null }) !== undefined, true);
});

test("derivados: devolve pacote novo com taxa_hz, sem mutar o original", () => {
    const derivar = criarCalculadorDerivados();
    const original = { millis: 1000, alt_baro: 10 };
    const r1 = derivar(original);
    assert.equal(r1.taxa_hz, null);
    assert.equal(original.taxa_hz, undefined);
    perto(derivar({ millis: 1500 }).taxa_hz, 2);
});

test("wrapDegrees", () => {
    assert.equal(wrapDegrees(190), -170);
    assert.equal(wrapDegrees(-190), 170);
    assert.equal(wrapDegrees(0), 0);
    assert.equal(wrapDegrees(360), 0);
});

test("atitude: primeiro pacote usa o acelerômetro; parado fica estável", () => {
    const a = criarAtitude();
    // gravidade só em Z => roll = pitch = 0
    assert.equal(atualizarAtitude(a, { millis: 0, gx: 0, gy: 0, gz: 0, ax: 0, ay: 0, az: 1 }), true);
    perto(a.roll, 0); perto(a.pitch, 0);
    for (let i = 1; i <= 50; i++) {
        atualizarAtitude(a, { millis: i * 100, gx: 0, gy: 0, gz: 0, ax: 0, ay: 0, az: 1 });
    }
    perto(a.roll, 0); perto(a.pitch, 0); perto(a.yaw, 0);
});

test("atitude: inclinação inicial vinda da gravidade (ay=1 => roll 90°)", () => {
    const a = criarAtitude();
    atualizarAtitude(a, { millis: 0, gx: 0, gy: 0, gz: 0, ax: 0, ay: 1, az: 0 });
    perto(a.roll, 90, 1e-9);
});

test("atitude: giroscópio integra o yaw (gz=36°/s por 1 s => 36°)", () => {
    const a = criarAtitude();
    atualizarAtitude(a, { millis: 0, gx: 0, gy: 0, gz: 36, ax: 0, ay: 0, az: 1 });
    for (let i = 1; i <= 10; i++) {
        atualizarAtitude(a, { millis: i * 100, gx: 0, gy: 0, gz: 36, ax: 0, ay: 0, az: 1 });
    }
    perto(a.yaw, 36, 1e-6);
});

test("atitude: em queda livre (|a|≈0) o acelerômetro é ignorado", () => {
    const a = criarAtitude();
    atualizarAtitude(a, { millis: 0, gx: 0, gy: 0, gz: 0, ax: 0, ay: 0, az: 1 });
    atualizarAtitude(a, { millis: 1000, gx: 10, gy: 0, gz: 0, ax: 0, ay: 0.01, az: 0.01 });
    perto(a.roll, 10, 1e-9);   // só giroscópio: 10°/s * 1 s
});

test("atitude: pacote sem giroscópio/millis não altera nada", () => {
    const a = criarAtitude();
    assert.equal(atualizarAtitude(a, { millis: 0, gx: null, gy: 0, gz: 0, ax: 0, ay: 0, az: 1 }), false);
    assert.equal(atualizarAtitude(a, { gx: 0, gy: 0, gz: 0 }), false);
    assert.equal(a.lastMillis, null);
});

test("atitude: salto de tempo > 2,5 s reinicia roll/pitch pelo acelerômetro", () => {
    const a = criarAtitude();
    atualizarAtitude(a, { millis: 0, gx: 0, gy: 0, gz: 0, ax: 0, ay: 0, az: 1 });
    atualizarAtitude(a, { millis: 10_000, gx: 500, gy: 0, gz: 0, ax: 0, ay: 1, az: 0 });
    perto(a.roll, 90, 1e-9);
});
