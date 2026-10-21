// stream.js — recebe a telemetria por SSE (Server-Sent Events).
//
// Eventos do servidor:
//   event: backlog  { pacotes: [...], idade_ultimo_s }   ao (re)conectar
//   (padrão)        { ...pacote }                        a cada pacote novo
//
// O EventSource reconecta sozinho; ao reconectar o servidor reenvia o backlog,
// por isso quem usa deve tratar "backlog" como substituição do histórico.

export function iniciarStream({ url = "/api/telemetry/stream", aoAbrir, aoBacklog, aoPacote, aoErro }) {
    const eventos = new EventSource(url);

    eventos.onopen = () => aoAbrir?.();

    eventos.addEventListener("backlog", (evento) => {
        try {
            const dados = JSON.parse(evento.data);
            aoBacklog?.(dados.pacotes ?? [], dados.idade_ultimo_s ?? null);
        } catch (erro) {
            console.error("Backlog de telemetria inválido:", erro);
        }
    });

    eventos.onmessage = (evento) => {
        try {
            aoPacote?.(JSON.parse(evento.data));
        } catch (erro) {
            console.error("JSON inválido recebido:", erro);
        }
    };

    eventos.onerror = () => aoErro?.();

    return eventos;
}
