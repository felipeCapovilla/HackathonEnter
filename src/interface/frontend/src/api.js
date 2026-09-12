const API = import.meta.env.VITE_API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8000/api`;
export const SESSION_EXPIRED = "enteragree:session-expired";

export function documentDownloadUrl(documentId) {
  return `${API}/documents/${encodeURIComponent(documentId)}/file`;
}

export async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(API + path, { credentials: "include", ...options });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Não foi possível conectar ao servidor. Tente novamente.");
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/") && !options.signal?.aborted) {
      window.dispatchEvent(new Event(SESSION_EXPIRED));
    }
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join("; ")
      : typeof detail === "string" ? detail : `Não foi possível concluir a solicitação (HTTP ${response.status}).`;
    throw new Error(message);
  }
  return data;
}

export function sendJson(path, body, method = "POST") {
  return request(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
