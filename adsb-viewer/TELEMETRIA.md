# Telemetria da CanSat dentro do visualizador ADS-B

O projeto agora é uma **estação de solo única**: o mesmo fluxo de linhas (serial, TCP, UDP, stdin ou replay)
alimenta o mapa ADS-B **e** o painel de telemetria (ex-`solo.py` + dashboard ITACUBE).

```
fonte de linhas ─┬─ "Msg:" … "Checksum:"  → MontadorPacote → TelemetryStore ─┬→ SSE  → /telemetria/
 (serial/tcp/…)  │                                                           └→ CSV  (launches/telemetriaN.csv)
                 └─ "adsb:…"              → parse_line     → AircraftStore  ──→ polling → /
```

## Como rodar

```bash
cd adsb_viewer
python -m src.main --replay sample_data/example_telemetria.log --replay-loop --open   # demo, sem hardware
python -m src.main --serial COM5 --open                                               # com o receptor (Windows)
python -m src.main --serial /dev/ttyUSB0 --open                                       # Linux
```

| Página            | O que mostra                                                    |
|-------------------|-----------------------------------------------------------------|
| `/`               | mapa + tabela ADS-B (como antes)                                |
| `/telemetria/`    | 3D da atitude, gráficos, painéis, botão **PING** (tecla `P`)    |

Opções novas: `--open`, `--no-telemetry`, `--telemetry-schema ARQ`, `--telemetry-history N`, `--csv-dir DIR`, `--no-csv`.

## Adicionar ou alterar um dado exibido

Tudo está em **`config/telemetry_schema.json`** (lido pelo Python *e* servido ao navegador).
Exemplo: o firmware passou a enviar `umidade` depois de `temp`.

1. Em `campos`, insira **na mesma posição em que o valor chega no pacote**:
   `{ "chave": "umidade", "rotulo": "Umidade", "unidade": "%", "casas": 1 }`
2. Para exibir, coloque `"umidade"` em `layout.paineis_laterais[].campos`, `layout.faixa_sensores[].campos`
   ou `layout.resumo`. Para um gráfico, adicione uma entrada em `layout.graficos`.

CSV, validação do pacote e JSON enviado ao navegador acompanham sozinhos. Erros no schema (chave repetida,
campo inexistente no layout, tipo inválido…) param o programa na partida com uma mensagem clara.

Campos **calculados no navegador** (ex.: `taxa_hz`) levam `"derivado": true` e o valor é devolvido em
`frontend/telemetria/js/derived.js`.

Para esconder um valor do painel 3D (GX/GY/GZ) ou do cabeçalho, edite o HTML: qualquer elemento com
`data-field="chave"` (e `data-casas="N"` opcional) é preenchido automaticamente.

## Formato do pacote serial

Um pacote tem várias linhas; começa em `Msg:` e termina em `Checksum`. Os **nomes são ignorados**, vale a
**ordem** dos valores (definida pelo schema):

```
Msg:rssi,snr,size   Id:..   Millis:..   Bat:vbat,ibat   Pos:lat,lon,alt   Baro:pressao,alt,temp
Acel:ax,ay,az       Giro:gx,gy,gz       Checksum:1
```

Linhas `adsb:`/`[LOG]`/`RX`/`TX`/`ER` intercaladas dentro do pacote não o corrompem. Se vier a quantidade errada de
valores, o pacote é aceito (faltantes = ausentes) e um `[WARN]` avisa — confira o schema e o firmware.

## API

| Rota                        | Descrição                                                         |
|-----------------------------|-------------------------------------------------------------------|
| `GET /api/telemetry/schema` | contrato de campos e layout                                       |
| `GET /api/telemetry/latest` | último pacote + contadores                                        |
| `GET /api/telemetry/stream` | SSE: evento `backlog` (histórico) + um evento por pacote          |
| `POST /api/telemetry/ping`  | envia `P` pela serial (só com `--serial`; barra origens externas) |
| `GET /api/health`           | inclui nº de pacotes e idade do último                            |

## Testes

```bash
python -m unittest discover -s tests -t .      # backend (Python)
node --test tests/js/*.test.mjs                # atitude, derivados, formatação (Node ≥ 18)
```

## O que mudou em relação ao `solo.py` + dashboard originais

- **CSV**: agora *anexa* cada pacote (antes reescrevia o arquivo inteiro a cada pacote); só cria o arquivo no
  primeiro pacote; mesmas colunas, separador `;` e `t_pc_iso`. Pasta padrão: `adsb_viewer/launches/`.
- **Ausentes**: JSON usa `null` (antes a string `"NaN"`); no CSV continua `NaN`.
- **PING**: o `p` do terminal virou botão/tecla `P` na página (funciona também sem terminal, ex.: pelo launcher).
- **Recarregar a página** não perde mais os gráficos: o servidor reenvia os últimos pacotes.
- **MIME**: o servidor serve `.css`/`.js` com o tipo correto, então o `ensureStylesheet` do `main.js` deixou de existir.
- **Serial**: reabre sozinha se o USB for desconectado e não consome 100 % de CPU esperando dados.
- `main.js` (2700 linhas) foi dividido em módulos ES em `frontend/telemetria/js/`; gráficos 2D e WebGL são o
  código original, sem mudança de lógica.
