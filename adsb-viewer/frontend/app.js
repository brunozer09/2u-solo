// app.js — consome GET /api/aircraft por polling e atualiza mapa + tabela.
//
// Por que polling e não WebSocket/SSE: o transporte estacao-de-solo ->
// visualizador ainda nao esta definido (CONTEXT.md 7) e o enlace via
// satelite pode ter latencia variavel e quedas (CONTEXT.md 5). Polling
// simples sobre HTTP e' o jeito mais tolerante a isso: cada tentativa e'
// independente, uma falha nao derruba uma conexao de longa duracao, e o
// front-end so precisa saber re-tentar no proximo intervalo.

const POLL_INTERVAL_MS = 1000;
const API_URL = "/api/aircraft";

// Centro/zoom iniciais: sobre o Brasil, ate que cheguem aeronaves com
// posicao conhecida (a estacao de solo de referencia deste projeto opera
// no Brasil - ver exemplos do CONTEXT.md). Ajuste livremente se a
// implantacao real for em outro lugar.
const CENTRO_INICIAL = [-15.5, -47.9];
const ZOOM_INICIAL = 4;

let map;
let marcadoresPorIcao = new Map(); // icao -> L.CircleMarker
let jaAjustouLimites = false;

const els = {
  statTotal: document.getElementById("stat-total"),
  statPosicionadas: document.getElementById("stat-posicionadas"),
  radarScope: document.getElementById("radar-scope"),
  statusText: document.getElementById("status-text"),
  statusLabel: document.getElementById("status-label"),
  statusMeta: document.getElementById("status-meta"),
  tableBody: document.getElementById("table-body"),
  tableEmptyState: document.getElementById("table-empty-state"),
  tableCountNote: document.getElementById("table-count-note"),
};

function initMap() {
  map = L.map("map", { zoomControl: true }).setView(CENTRO_INICIAL, ZOOM_INICIAL);

  // Basemap padrão do OpenStreetMap (tiles + dados abertos, sem chave de
  // API). Os tiles são claros por padrão; um leve ajuste de brilho/
  // saturação em .leaflet-tile-pane (style.css) evita um contraste muito
  // brusco contra o restante da UI escura, sem fingir ser um "dark mode".
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    subdomains: "abc",
    maxZoom: 19,
  }).addTo(map);
}

function formatarValor(valor, casasDecimais) {
  if (valor === null || valor === undefined) {
    return null;
  }
  if (typeof casasDecimais === "number") {
    return Number(valor).toFixed(casasDecimais);
  }
  return String(valor);
}

function formatarIdade(segundos) {
  if (segundos < 1) return "agora";
  if (segundos < 60) return `${Math.floor(segundos)}s`;
  const minutos = Math.floor(segundos / 60);
  if (minutos < 60) return `${minutos}min`;
  const horas = Math.floor(minutos / 60);
  return `${horas}h${minutos % 60}min`;
}

function formatarTimestamp(ts) {
  if (ts === null || ts === undefined) return null;
  const data = new Date(ts * 1000);                 // epoch em segundos -> ms
  if (Number.isNaN(data.getTime())) return null;
  return data.toLocaleTimeString("pt-BR");          // HH:MM:SS no fuso do navegador
}

function celulaOuAusente(valorFormatado) {
  if (valorFormatado === null) {
    return '<span class="value-missing">&mdash;</span>';
  }
  return valorFormatado;
}

function atualizarMapa(listaAeronaves) {
  const icaosVistos = new Set();

  for (const aero of listaAeronaves) {
    if (aero.latitude === null || aero.longitude === null) {
      continue; // sem posicao conhecida: nunca plotar (CONTEXT.md 4.1)
    }
    icaosVistos.add(aero.icao);

    const cor = aero.stale ? "#E0A458" : "#6098E3";
    const opacidade = aero.stale ? 0.55 : 0.95;

    let marcador = marcadoresPorIcao.get(aero.icao);
    if (!marcador) {
      marcador = L.circleMarker([aero.latitude, aero.longitude], {
        radius: 6,
        weight: 2,
        color: cor,
        fillColor: cor,
        fillOpacity: opacidade,
        opacity: opacidade,
      }).addTo(map);
      marcador.bindPopup("", { className: "aircraft-popup" });
      marcadoresPorIcao.set(aero.icao, marcador);
    } else {
      marcador.setLatLng([aero.latitude, aero.longitude]);
      marcador.setStyle({ color: cor, fillColor: cor, fillOpacity: opacidade, opacity: opacidade });
    }

    const alt = celulaOuAusente(formatarValor(aero.altitude, 0));
    const spd = celulaOuAusente(formatarValor(aero.air_speed, 1));
    const ts = celulaOuAusente(formatarTimestamp(aero.ultimo_timestamp));

    marcador.setPopupContent(
      `<div class="popup-title">${aero.icao}</div>` +
        `<div class="popup-row"><span>Altitude</span><span>${alt} ft</span></div>` +
        `<div class="popup-row"><span>Velocidade (ar)*</span><span>${spd} kt</span></div>` +
        `<div class="popup-row"><span>Atualizado há</span><span>${formatarIdade(aero.idade_segundos)}</span></div>` +
        `<div class="popup-row"><span>Última mensagem</span><span>${ts}</span></div>`
    );
  }

  // Remove marcadores de aeronaves que sairam do store (expiraram por
  // remove_after) - o store nao emite um evento de "aeronave saiu de
  // alcance", entao a unica forma de saber e' comparar com o snapshot
  // atual (CONTEXT.md 2.4 / 7).
  for (const [icao, marcador] of marcadoresPorIcao.entries()) {
    if (!icaosVistos.has(icao)) {
      map.removeLayer(marcador);
      marcadoresPorIcao.delete(icao);
    }
  }

  if (!jaAjustouLimites && icaosVistos.size > 0) {
    const bounds = L.latLngBounds(
      [...marcadoresPorIcao.values()].map((m) => m.getLatLng())
    );
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 9 });
    jaAjustouLimites = true;
  }

  return icaosVistos.size;
}

function atualizarTabela(listaAeronaves) {
  if (listaAeronaves.length === 0) {
    els.tableBody.innerHTML = "";
    els.tableEmptyState.style.display = "block";
    return;
  }
  els.tableEmptyState.style.display = "none";

  const linhas = listaAeronaves.map((aero) => {
    const lat = celulaOuAusente(formatarValor(aero.latitude, 5));
    const lon = celulaOuAusente(formatarValor(aero.longitude, 5));
    const alt = celulaOuAusente(formatarValor(aero.altitude, 0));
    const spd = celulaOuAusente(formatarValor(aero.air_speed, 1));
    const ts = celulaOuAusente(formatarTimestamp(aero.ultimo_timestamp));
    const badge = aero.stale
      ? '<span class="badge badge-stale">stale</span>'
      : '<span class="badge badge-live">ao vivo</span>';

    return (
      `<tr class="${aero.stale ? "is-stale" : ""}">` +
      `<td>${aero.icao}</td>` +
      `<td>${lat}</td>` +
      `<td>${lon}</td>` +
      `<td>${alt}</td>` +
      `<td>${spd}</td>` +
      `<td>${ts}</td>` +
      `<td>${formatarIdade(aero.idade_segundos)}</td>` +
      `<td>${badge}</td>` +
      `</tr>`
    );
  });

  els.tableBody.innerHTML = linhas.join("");
}

function marcarOnline(dados, numeroComPosicao) {
  els.radarScope.classList.remove("is-offline");
  els.statusText.classList.remove("is-offline");
  els.statusLabel.textContent = "AO VIVO";
  const horaServidor = new Date(dados.server_time * 1000);
  els.statusMeta.textContent = horaServidor.toLocaleTimeString("pt-BR");
  els.statTotal.textContent = dados.aircraft.length;
  els.statPosicionadas.textContent = numeroComPosicao;
  els.tableCountNote.textContent = `${dados.aircraft.length} rastreada(s)`;
}

function marcarOffline(erro) {
  els.radarScope.classList.add("is-offline");
  els.statusText.classList.add("is-offline");
  els.statusLabel.textContent = "SEM CONEXÃO";
  els.statusMeta.textContent = "tentando novamente…";
  console.warn("Falha ao consultar /api/aircraft:", erro);
}

async function pollOnce() {
  try {
    const resposta = await fetch(API_URL, { cache: "no-store" });
    if (!resposta.ok) {
      throw new Error(`HTTP ${resposta.status}`);
    }
    const dados = await resposta.json();
    const numeroComPosicao = atualizarMapa(dados.aircraft);
    atualizarTabela(dados.aircraft);
    marcarOnline(dados, numeroComPosicao);
  } catch (erro) {
    marcarOffline(erro);
  }
}

function iniciar() {
  initMap();
  pollOnce();
  setInterval(pollOnce, POLL_INTERVAL_MS);
}

document.addEventListener("DOMContentLoaded", iniciar);
