// Chamadas HTTP e leitor de SSE.

function errorMessage(body, status) {
  const detail = body && body.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    // Erros de validação do Pydantic: tira o prefixo técnico.
    return detail.map((d) => String(d.msg || '').replace(/^Value error, /, '')).join(' ');
  }
  return `Erro ${status}`;
}

export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* resposta sem corpo */ }
  if (!res.ok) throw new Error(errorMessage(data, res.status));
  return data;
}

/**
 * POST que devolve SSE (`data: {json}`). Chama onEvent para cada evento.
 * Linhas partidas entre pacotes são acumuladas no buffer, nada se perde.
 */
export async function streamSSE(path, body, onEvent, signal) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let data = null;
    try { data = await res.json(); } catch { /* ignore */ }
    throw new Error(errorMessage(data, res.status));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line.startsWith('data:')) continue;
      try {
        await onEvent(JSON.parse(line.slice(5).trim()));
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }
}
