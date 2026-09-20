import { createSession, listScenarios, submitTurn } from "./api.js";
import { playResponse, stopAudio } from "./audio.js";

const el = (id) => document.getElementById(id);
const recognitionType = window.SpeechRecognition || window.webkitSpeechRecognition;
let sessionId = null;
let busy = false;
let completed = false;
let recognition = null;
let listening = false;
let scenarios = [];
let catalogReady = false;
let scenarioName = "Fictional bank fraud";
const label = (value) => String(value).replaceAll("_", " ");

function setBusy(value) {
  busy = value;
  el("start").disabled = busy || !catalogReady;
  el("scenario").disabled = busy || !catalogReady || (!!sessionId && !completed);
  el("another-scenario").disabled = busy;
  const disabled = busy || !sessionId || completed;
  el("send").disabled = disabled || listening;
  el("participant-text").disabled = disabled;
  el("microphone").disabled = disabled || !recognitionType;
}

function selectedScenarioDescription() {
  const scenario = scenarios.find((item) => item.id === el("scenario").value);
  el("scenario-description").textContent = scenario
    ? `${scenario.description} Fictional organization: ${scenario.fictional_organization}.`
    : "The default fictional bank scenario is available. Restart the server or reload to retry the catalog.";
}

async function loadScenarios() {
  try {
    scenarios = await listScenarios();
    el("scenario").replaceChildren();
    for (const scenario of scenarios) {
      const option = document.createElement("option");
      option.value = scenario.id;
      option.textContent = scenario.display_name;
      el("scenario").append(option);
    }
    if (!scenarios.length) throw new Error("No scenarios available");
  } catch {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Fictional bank fraud (default)";
    el("scenario").replaceChildren(option);
    el("status").textContent = "Scenario catalog unavailable. You can still try the default simulation.";
  } finally {
    catalogReady = true;
    selectedScenarioDescription();
    setBusy(false);
  }
}

el("scenario").addEventListener("change", selectedScenarioDescription);
el("another-scenario").addEventListener("click", () => {
  stopListening();
  stopAudio(el("audio"));
  sessionId = null;
  completed = false;
  setBusy(false);
  el("start").textContent = "Start simulation";
  el("status").textContent = "Choose your next scenario above, then start the simulation. Your previous debrief stays visible until you start.";
  el("scenario").focus();
});

function message(speaker, text) {
  el("transcript").querySelector(".empty")?.remove();
  const article = document.createElement("article");
  article.className = speaker === "You" ? "message participant" : "message caller";
  const title = document.createElement("strong");
  title.textContent = speaker;
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  article.append(title, paragraph);
  el("transcript").append(article);
  article.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function stageUpdate(stage, risk = 0) {
  el("stage").textContent = label(stage);
  el("risk").value = risk;
  el("risk-value").textContent = `${Math.round(risk * 100)}%`;
}

function timeline(text) {
  const item = document.createElement("li");
  item.textContent = text;
  el("timeline").append(item);
}

function stopListening() {
  recognition?.abort();
  listening = false;
  el("microphone").textContent = "Use microphone";
}

el("start").addEventListener("click", async () => {
  stopListening();
  stopAudio(el("audio"));
  setBusy(true);
  el("status").textContent = "Starting the simulation and preparing the synthetic voice…";
  try {
    const data = await createSession(el("scenario").value);
    sessionId = data.session_id;
    completed = false;
    scenarioName = data.scenario_name || scenarios.find((item) => item.id === data.scenario_id)?.display_name || "Fictional bank fraud";
    el("selected-scenario").textContent = `Practicing: ${scenarioName}`;
    el("debrief").hidden = true;
    el("transcript").replaceChildren();
    el("timeline").replaceChildren();
    el("participant-text").value = "";
    el("intent").textContent = "—";
    el("evidence").textContent = "—";
    el("tactics").textContent = (data.tactics_triggered || ["authority"]).map(label).join(", ") || "—";
    stageUpdate(data.stage, data.risk_score);
    timeline(`Opening → ${label(data.stage)}`);
    message("Simulated caller", data.scammer_text);
    el("providers").textContent = data.voice_fallback ? "Voice: text-only fallback" : "Voice: ElevenLabs";
    el("start").textContent = "Restart simulation";
    el("status").textContent = "Your turn. Use a fictional response only.";
    await playResponse(el("audio"), el("audio-status"), data.audio_url);
  } catch (error) {
    el("status").textContent = error.message || "Unable to reach the backend. Check that it is running.";
  } finally {
    setBusy(false);
    if (sessionId && !completed) el("participant-text").focus();
  }
});

el("turn-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = el("participant-text").value.trim();
  if (busy || completed || !sessionId || !text) return;
  stopListening();
  stopAudio(el("audio"));
  setBusy(true);
  el("status").textContent = "Classifying your response, selecting the branch, and preparing audio…";
  try {
    const data = await submitTurn(sessionId, text);
    message("You", data.participant_text);
    completed = data.completed || ["safe_exit", "risky_outcome"].includes(data.stage_after);
    message(completed ? "Training debrief" : "Simulated caller", data.scammer_text);
    stageUpdate(data.stage_after, data.risk_score);
    el("tactics").textContent = data.tactics_triggered.map(label).join(", ") || "—";
    el("intent").textContent = `${label(data.analysis.participant_intent)} · ${Math.round(data.analysis.confidence * 100)}% confidence`;
    el("evidence").textContent = data.analysis.evidence_span;
    const fallbackReason = data.classifier_fallback_reason === "timeout" ? " (timeout)" : "";
    el("providers").textContent = `Classifier: ${data.classifier_fallback ? `deterministic fallback${fallbackReason}` : data.classifier_provider} · Voice: ${data.voice_fallback ? "text-only fallback" : data.voice_provider}`;
    timeline(`${label(data.stage_before)} → ${label(data.stage_after)} · ${label(data.analysis.participant_intent)} · tactics: ${data.tactics_triggered.map(label).join(", ") || "none"} · risk ${Math.round((data.risk_before ?? 0) * 100)}% → ${Math.round(data.risk_score * 100)}% · ${Math.round(data.analysis.confidence * 100)}% confidence · evidence: “${data.analysis.evidence_span}”`);
    if (completed) {
      el("debrief-heading").textContent = `${data.debrief?.scenario_name || scenarioName} — debrief`;
      el("debrief-outcome").textContent = `Outcome: ${label(data.debrief?.outcome || data.stage_after)}`;
      el("debrief-summary").textContent = data.debrief?.summary || data.scammer_text;
      el("debrief-guidance").replaceChildren();
      const guidance = data.debrief?.safer_response_guidance || ["End the unexpected conversation and independently verify through an official channel you already trust."];
      for (const advice of Array.isArray(guidance) ? guidance : [guidance]) {
        const item = document.createElement("li");
        item.textContent = advice;
        el("debrief-guidance").append(item);
      }
      el("debrief").hidden = false;
    }
    el("participant-text").value = "";
    el("status").textContent = completed ? "Exercise complete. Review the evidence and timeline, or start again to try another response." : "Your turn. Notice how the caller's tactic changed.";
    await playResponse(el("audio"), el("audio-status"), data.audio_url);
  } catch (error) {
    el("status").textContent = error.message || "Unable to reach the backend. Your response has been kept.";
  } finally {
    setBusy(false);
    if (!completed) el("participant-text").focus();
  }
});

if (!recognitionType) {
  el("microphone").textContent = "Microphone unavailable";
  el("microphone").title = "This browser does not support speech recognition. Type your response instead.";
} else {
  el("microphone").addEventListener("click", () => {
    if (listening) { stopListening(); setBusy(busy); return; }
    recognition = new recognitionType();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      el("participant-text").value = event.results[0][0].transcript.slice(0, 1000);
      el("status").textContent = "Review the recognized text, then send it. Never include real personal information.";
    };
    recognition.onerror = () => { el("status").textContent = "Speech recognition is unavailable or permission was denied. Type your response instead."; };
    recognition.onend = () => { listening = false; el("microphone").textContent = "Use microphone"; setBusy(busy); };
    try {
      recognition.start();
      listening = true;
      el("microphone").textContent = "Stop microphone";
      el("status").textContent = "Listening. Your browser's speech service may process microphone audio. Use fictional responses only.";
      setBusy(busy);
    } catch {
      stopListening();
      el("status").textContent = "Could not start the microphone. Type your response instead.";
    }
  });
}
el("audio").addEventListener("error", () => { el("audio-status").textContent = "Audio could not be loaded. Continue with the transcript."; });
loadScenarios();
