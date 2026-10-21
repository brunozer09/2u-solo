// attitude.js — estimativa de atitude (roll/pitch/yaw) por filtro complementar.
//
// Mesma matemática do dashboard original, agora como função pura sobre um
// objeto de estado (testável sem navegador e sem WebGL):
//
//   const atitude = criarAtitude();
//   if (atualizarAtitude(atitude, pacote)) renderer.setRotation(atitude.roll, atitude.pitch, atitude.yaw);
//
// - O giroscópio é integrado (preciso em movimento rápido, mas acumula drift).
// - O acelerômetro (direção da gravidade) corrige roll/pitch lentamente, mas só
//   quando |a| está perto de 1 g (fora disso — queda livre, impacto — é ignorado).
// - O yaw vem só do giroscópio (sem magnetômetro) e portanto deriva com o tempo.

import { finiteNumber } from "./format.js";

const ALPHA = 0.96;
const FAIXA_G = Object.freeze({ min: 0.55, max: 1.45 });
const SALTO_MAX_S = 2.5;
const RAD_PARA_GRAUS = 180 / Math.PI;

export function criarAtitude() {
    return { roll: 0, pitch: 0, yaw: 0, lastMillis: null };
}

export function wrapDegrees(value) {
    return (((value + 180) % 360) + 360) % 360 - 180;
}

function rollPitchDoAcelerometro(ax, ay, az) {
    return {
        roll: Math.atan2(ay, az) * RAD_PARA_GRAUS,
        pitch: Math.atan2(-ax, Math.hypot(ay, az)) * RAD_PARA_GRAUS
    };
}

/** Atualiza `atitude` com o pacote. Devolve true se houve nova orientação. */
export function atualizarAtitude(atitude, pacote) {
    const gx = finiteNumber(pacote.gx);
    const gy = finiteNumber(pacote.gy);
    const gz = finiteNumber(pacote.gz);
    const ax = finiteNumber(pacote.ax);
    const ay = finiteNumber(pacote.ay);
    const az = finiteNumber(pacote.az);
    const millis = finiteNumber(pacote.millis);

    if (gx === null || gy === null || gz === null || millis === null) {
        return false;
    }

    const temAcelerometro = ax !== null && ay !== null && az !== null;

    const dt = atitude.lastMillis !== null
        ? (millis - atitude.lastMillis) / 1000
        : null;

    atitude.lastMillis = millis;

    // Primeiro pacote ou salto de tempo: reinicia roll/pitch pelo acelerômetro.
    if (dt === null || dt < 0 || dt > SALTO_MAX_S) {
        if (temAcelerometro) {
            const inicial = rollPitchDoAcelerometro(ax, ay, az);
            atitude.roll = inicial.roll;
            atitude.pitch = inicial.pitch;
        }
        return true;
    }

    // Integração do giroscópio.
    const rollPrevisto = atitude.roll + gx * dt;
    const pitchPrevisto = atitude.pitch + gy * dt;
    atitude.yaw = wrapDegrees(atitude.yaw + gz * dt);

    const modulo = temAcelerometro ? Math.hypot(ax, ay, az) : null;

    if (modulo !== null && modulo > FAIXA_G.min && modulo < FAIXA_G.max) {
        const medido = rollPitchDoAcelerometro(ax, ay, az);
        atitude.roll = ALPHA * rollPrevisto + (1 - ALPHA) * medido.roll;
        atitude.pitch = ALPHA * pitchPrevisto + (1 - ALPHA) * medido.pitch;
    } else {
        atitude.roll = rollPrevisto;
        atitude.pitch = pitchPrevisto;
    }

    atitude.roll = wrapDegrees(atitude.roll);
    atitude.pitch = wrapDegrees(atitude.pitch);

    return true;
}
