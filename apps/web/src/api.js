// Same-origin in the integrated app; separate development frontend on port 3000/5173.
export const API_BASE = ["3000", "5173"].includes(location.port)
  ? "http://localhost:8000"
  : location.origin;

async function request(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    // Never render raw upstream errors or request bodies.
    if (response.status === 404) throw new Error("Session not found. Start a new simulation.");
    if (response.status === 409) throw new Error("This session has finished. Start a new simulation.");
    if (response.status === 422) throw new Error(path === "/api/sessions"
      ? "That scenario is unavailable. Reload the page and choose an available scenario."
      : "Enter a fictional response of 1–2000 characters.");
    throw new Error(`The request could not be completed (${response.status}). Please try again.`);
  }
  return response.json();
}

export const listScenarios = () => request("/api/scenarios");
export const createSession = (scenarioId) => request("/api/sessions", scenarioId ? { scenario_id: scenarioId } : {});
export const submitTurn = (sessionId, text) => request(`/api/sessions/${encodeURIComponent(sessionId)}/turns`, { participant_text: text });
