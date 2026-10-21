// schema.js — carrega o contrato dos campos servido pelo backend.
//
// A fonte da verdade é config/telemetry_schema.json (lido também pelo Python
// para saber a ordem dos valores do pacote serial).

export async function carregarSchema(url = "/api/telemetry/schema") {
    const resposta = await fetch(url, { cache: "no-store" });

    if (!resposta.ok) {
        throw new Error(`HTTP ${resposta.status} ao carregar ${url}`);
    }

    const dados = await resposta.json();

    return {
        ...dados,
        // chave -> definição do campo, para consulta O(1)
        campos: new Map(dados.campos.map((campo) => [campo.chave, campo]))
    };
}
