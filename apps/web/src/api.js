// Same-origin in the integrated app; separate development frontend on port 3000/5173.
export const API_BASE = ["3000", "5173"].includes(location.port)
  ? "http://localhost:8000"
  : location.origin;

async function request(path, body) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("The simulation server could not be reached. Check that it is running, then try again.");
  }
  if (!response.ok) {
    // Never render raw upstream errors or request bodies.
    if (response.status === 404) throw new Error("Session not found. Start a new simulation.");
    if (response.status === 409) {
      let payload = {};
      try { payload = await response.json(); } catch { /* use the safe generic message */ }
      const error = new Error(payload.detail || "This call has ended. Start a new simulation.");
      error.retryAvailable = payload.retry_available === true;
      throw error;
    }
    if (response.status === 422) throw new Error(path === "/api/sessions"
      ? "That scenario is unavailable. Reload the page and choose an available scenario."
      : "Enter a fictional response of 1–2000 characters.");
    if (response.status === 503) {
      let payload = {};
      try { payload = await response.json(); } catch { /* use the safe generic message */ }
      if (/^ollama_(?:unavailable|timeout|invalid_output)$/.test(String(payload.dialogue_provider || ""))) {
        const error = new Error(payload.detail || "Local caller is unavailable. Confirm Ollama is running, then press Retry caller response.");
        error.dialogueUnavailable = true;
        error.retryAvailable = payload.retry_available !== false;
        error.dialogueProvider = payload.dialogue_provider;
        throw error;
      }
    }
    throw new Error(`The request could not be completed (${response.status}). Please try again.`);
  }
  try {
    return await response.json();
  } catch {
    throw new Error("The simulation server returned an unreadable response. Please try again.");
  }
}

export const listScenarios = () => request("/api/scenarios");
export const createSession = (scenarioId, interactionMode = "text") => request(
  "/api/sessions",
  scenarioId ? { scenario_id: scenarioId, interaction_mode: interactionMode } : { interaction_mode: interactionMode },
);
export const submitTurn = (sessionId, text, inputMode = "text") => request(
  `/api/sessions/${encodeURIComponent(sessionId)}/turns`,
  { participant_text: text, input_mode: inputMode },
);
export const endCall = (sessionId) => request(
  `/api/sessions/${encodeURIComponent(sessionId)}/end`,
  {},
);
export const retryDialogue = (sessionId) => request(
  `/api/sessions/${encodeURIComponent(sessionId)}/dialogue/retry`,
  {},
);
export const getEvaluation = (sessionId) => request(
  `/api/sessions/${encodeURIComponent(sessionId)}/evaluation`,
);
