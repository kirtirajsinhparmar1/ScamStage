import { createSession, getEvaluation, listScenarios, submitTurn } from "./api.js";
import { playResponse, stopAudio } from "./audio.js";
import { VoiceCallController } from "./voice.js";

const el = (id) => document.getElementById(id);
const recognitionType = window.SpeechRecognition || window.webkitSpeechRecognition;
const TERMINAL_STAGES = new Set(["safe_exit", "risky_outcome"]);
const label = (value) => String(value).replaceAll("_", " ");

let sessionId = null;
let busy = false;
let completed = false;
let recognition = null;
let listening = false;
let scenarios = [];
let catalogReady = false;
let scenarioName = "Fictional bank fraud";
let voiceMode = false;
let voiceCall;
let evaluationPollGeneration = 0;
let evaluationTimer = null;

function callIsLocked() {
  if (!voiceMode || !voiceCall?.active) return false;
  return !["idle", "terminal", "error"].includes(voiceCall.state);
}

function setBusy(value) {
  busy = value;
  const locked = callIsLocked();
  const voiceStarting = voiceMode && voiceCall?.state === "idle" && !sessionId;
  const typedFallback = voiceMode && voiceCall?.typedFallback;
  el("start").disabled = busy || voiceStarting || !catalogReady || locked;
  el("start-voice").disabled = busy || voiceStarting || !catalogReady || locked;
  el("scenario").disabled = busy || voiceStarting || !catalogReady || locked;
  el("another-scenario").disabled = busy || locked;
  const disabled = busy || !sessionId || completed || (voiceMode && !typedFallback);
  el("send").disabled = disabled || listening;
  el("participant-text").disabled = disabled;
  el("microphone").disabled = disabled || !recognitionType || voiceMode;
  el("turn-form").setAttribute("aria-busy", String(busy));
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

function emptyMessage(text) {
  const paragraph = document.createElement("p");
  paragraph.className = "empty";
  paragraph.textContent = text;
  return paragraph;
}

function clearExperience(statusText) {
  cancelEvaluationPolling();
  voiceMode = false;
  voiceCall?.reset();
  stopListening();
  stopAudio(el("audio"));
  sessionId = null;
  completed = false;
  scenarioName = "Fictional bank fraud";
  el("voice-call").hidden = true;
  el("selected-scenario").textContent = "No active scenario";
  el("debrief").hidden = true;
  el("debrief-outcome").textContent = "";
  el("debrief-summary").textContent = "";
  el("debrief-tactics").textContent = "";
  el("debrief-guidance").replaceChildren();
  renderEvaluation(null);
  el("transcript").replaceChildren(emptyMessage("Start the selected scenario. Your choices determine what happens next."));
  const firstDecision = document.createElement("li");
  firstDecision.textContent = "No decisions yet";
  el("timeline").replaceChildren(firstDecision);
  el("participant-text").value = "";
  el("intent").textContent = "—";
  el("evidence").textContent = "—";
  el("tactics").textContent = "—";
  el("providers").textContent = "Waiting for a session";
  el("audio-status").textContent = "Audio appears here when available.";
  el("voice-support").textContent = "Speech recognition is checked when the call starts.";
  el("start").textContent = "Start simulation";
  el("start-voice").textContent = "Start voice call";
  el("send").textContent = "Send response";
  el("status").textContent = statusText;
  stageUpdate("Not started", 0);
}

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
  recognition = null;
  listening = false;
  el("microphone").textContent = "Use microphone";
}

function providerSummary(data) {
  let classifier = data.classifier_provider || "unknown";
  if (data.classifier_fallback) {
    const reason = data.classifier_fallback_reason === "timeout" ? " (timeout)" : "";
    classifier = `deterministic fallback${reason}`;
  }
  const voiceProvider = data.voice_provider === "elevenlabs" ? "ElevenLabs" : data.voice_provider;
  const voice = data.voice_fallback ? "text-only fallback" : (voiceProvider || "ElevenLabs");
  const dialogueLabels = {
    ollama: "Ollama",
    ollama_unavailable: "Ollama unavailable",
    ollama_timeout: "Ollama timeout",
    ollama_invalid_output: "Ollama invalid output",
    gemini: "Gemini",
    authored_fallback: "authored fallback",
  };
  const dialogue = dialogueLabels[data.dialogue_provider]
    || (data.dialogue_fallback ? "authored fallback" : (data.dialogue_provider || "unknown"));
  return `Safety policy: ${classifier} · Caller dialogue: ${dialogue} · Voice: ${voice}`;
}

function dialogueWarning(data) {
  return /^ollama_(?:unavailable|timeout|invalid_output)$/.test(String(data?.dialogue_provider || ""))
    ? "Local caller is unavailable. Confirm Ollama is running, then restart the simulation."
    : "";
}

function cancelEvaluationPolling() {
  evaluationPollGeneration += 1;
  if (evaluationTimer) window.clearTimeout(evaluationTimer);
  evaluationTimer = null;
}

function renderEvaluation(data) {
  const card = el("evaluation-card");
  if (!data?.status) {
    card.hidden = true;
    el("evaluation-status").textContent = "";
    el("evaluation-summary").textContent = "";
    el("evaluation-safety").textContent = "";
    el("evaluation-tactics").textContent = "";
    el("evaluation-risk").textContent = "";
    el("evaluation-confidence").textContent = "";
    el("evaluation-evidence").replaceChildren();
    return;
  }
  card.hidden = false;
  const provider = data.provider === "nemotron" ? "NVIDIA Nemotron" : "deterministic fallback";
  if (data.status === "pending") {
    el("evaluation-status").textContent = "Independent evaluation: pending";
    el("evaluation-summary").textContent = "The immediate deterministic debrief remains authoritative while the independent review is attempted.";
  } else if (data.status === "complete" && data.result) {
    const result = data.result;
    el("evaluation-status").textContent = `Independent evaluation: ${provider}`;
    el("evaluation-summary").textContent = result.adaptation_summary;
    el("evaluation-safety").textContent = result.participant_safety_summary;
    el("evaluation-tactics").textContent = `Evaluated tactics: ${(result.tactics_detected || []).map(label).join(", ") || "none"}`;
    el("evaluation-risk").textContent = `Overall evaluated risk: ${Math.round(result.overall_risk * 100)}% · Outcome: ${label(result.participant_outcome)}`;
    el("evaluation-confidence").textContent = `Confidence: ${Math.round(result.confidence * 100)}%`;
    el("evaluation-evidence").replaceChildren();
    for (const evidence of result.evidence || []) {
      const item = document.createElement("li");
      item.textContent = `Turn ${evidence.turn}: “${evidence.quote}” — ${evidence.reason}`;
      el("evaluation-evidence").append(item);
    }
  } else {
    el("evaluation-status").textContent = data.status === "fallback"
      ? "Independent evaluation: deterministic fallback"
      : "Independent evaluation unavailable";
    el("evaluation-summary").textContent = "No independent provider result was accepted. The deterministic scenario debrief is retained as the source of truth.";
    el("evaluation-safety").textContent = "";
    el("evaluation-tactics").textContent = "";
    el("evaluation-risk").textContent = "";
    el("evaluation-confidence").textContent = "";
    el("evaluation-evidence").replaceChildren();
  }
}

function pollEvaluation(sessionAtStart) {
  cancelEvaluationPolling();
  const generation = evaluationPollGeneration;
  const poll = async (attempt) => {
    if (generation !== evaluationPollGeneration || sessionId !== sessionAtStart) return;
    try {
      const data = await getEvaluation(sessionAtStart);
      if (generation !== evaluationPollGeneration || sessionId !== sessionAtStart) return;
      renderEvaluation(data);
      if (data.status === "pending" && attempt < 5) {
        evaluationTimer = window.setTimeout(() => void poll(attempt + 1), 700);
      }
    } catch {
      renderEvaluation({ status: "unavailable" });
    }
  };
  void poll(0);
}

function renderDebrief(data) {
  const debrief = data.debrief;
  if (!debrief) return;
  el("debrief-heading").textContent = `${debrief.scenario_name || scenarioName} — debrief`;
  el("debrief-outcome").textContent = `Outcome: ${label(debrief.outcome || data.stage_after)}`;
  el("debrief-summary").textContent = debrief.summary || data.scammer_text;
  const tactics = debrief.tactics_observed || [];
  el("debrief-tactics").textContent = tactics.length ? `Tactics observed: ${tactics.map(label).join(", ")}` : "";
  el("debrief-guidance").replaceChildren();
  const guidance = debrief.safer_response_guidance || ["End the unexpected conversation and independently verify through an official channel you already trust."];
  for (const advice of Array.isArray(guidance) ? guidance : [guidance]) {
    const item = document.createElement("li");
    item.textContent = advice;
    el("debrief-guidance").append(item);
  }
  renderEvaluation(debrief);
  if (debrief.evaluation_status === "pending" && sessionId) pollEvaluation(sessionId);
  el("debrief").hidden = false;
}

function renderSession(data) {
  sessionId = data.session_id;
  completed = false;
  scenarioName = data.scenario_name || scenarios.find((item) => item.id === data.scenario_id)?.display_name || "Fictional bank fraud";
  const selected = scenarios.find((item) => item.id === data.scenario_id);
  const callerName = selected?.fictional_organization || scenarioName;
  el("voice-heading").textContent = callerName;
  el("caller-avatar").textContent = callerName.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
  el("selected-scenario").textContent = `Practicing: ${scenarioName}`;
  el("debrief").hidden = true;
  renderEvaluation(null);
  el("transcript").replaceChildren();
  el("timeline").replaceChildren();
  el("participant-text").value = "";
  el("intent").textContent = "—";
  el("evidence").textContent = "—";
  el("tactics").textContent = (data.tactics_triggered || ["authority"]).map(label).join(", ") || "—";
  el("providers").textContent = providerSummary({
    voice_fallback: data.voice_fallback,
    dialogue_provider: data.dialogue_provider,
    dialogue_fallback: data.dialogue_fallback,
    classifier_provider: "fast_safety_policy",
  });
  stageUpdate(data.stage, data.risk_score);
  timeline(`Opening → ${label(data.stage)}`);
  message("Simulated caller", data.scammer_text);
}

function renderTurn(data) {
  message("You", data.participant_text);
  const terminal = data.completed || TERMINAL_STAGES.has(data.stage_after);
  message(terminal ? "Training debrief" : "Simulated caller", data.scammer_text);
  completed = terminal;
  stageUpdate(data.stage_after, data.risk_score);
  el("tactics").textContent = (data.tactics_triggered || []).map(label).join(", ") || "—";
  el("intent").textContent = `${label(data.analysis.participant_intent)} · ${Math.round(data.analysis.confidence * 100)}% confidence`;
  el("evidence").textContent = data.analysis.evidence_span;
  el("providers").textContent = providerSummary(data);
  const warning = dialogueWarning(data);
  if (warning) el("voice-support").textContent = warning;
  timeline(`${label(data.stage_before)} → ${label(data.stage_after)} · ${label(data.analysis.participant_intent)} · tactics: ${(data.tactics_triggered || []).map(label).join(", ") || "none"} · risk ${Math.round((data.risk_before ?? 0) * 100)}% → ${Math.round(data.risk_score * 100)}% · ${Math.round(data.analysis.confidence * 100)}% confidence · evidence: “${data.analysis.evidence_span}”`);
  if (terminal) renderDebrief(data);
  el("participant-text").value = "";
}

el("scenario").addEventListener("change", () => {
  selectedScenarioDescription();
  if (sessionId || completed) {
    clearExperience("Scenario changed. Start the selected fictional simulation when you are ready.");
    setBusy(false);
  }
});

el("another-scenario").addEventListener("click", () => {
  clearExperience("Choose your next scenario above, then start the simulation.");
  setBusy(false);
  el("scenario").focus();
});

el("start").addEventListener("click", async () => {
  clearExperience("Starting the simulation and preparing the synthetic voice…");
  setBusy(true);
  el("start").textContent = "Starting…";
  try {
    const data = await createSession(el("scenario").value, "text");
    renderSession(data);
    el("start").textContent = "Restart simulation";
    el("status").textContent = "Your turn. Use a fictional response only.";
    await playResponse(el("audio"), el("audio-status"), data.audio_url);
  } catch (error) {
    el("status").textContent = error.message || "Unable to reach the backend. Check that it is running.";
  } finally {
    el("start").textContent = sessionId ? "Restart simulation" : "Start simulation";
    setBusy(false);
    if (sessionId && !completed) el("participant-text").focus();
  }
});

el("turn-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = el("participant-text").value.trim();
  if (!text) return;
  if (voiceMode) {
    if (voiceCall?.typedFallback) await voiceCall.submitTyped(text);
    return;
  }
  if (busy || completed || !sessionId) return;
  stopListening();
  stopAudio(el("audio"));
  setBusy(true);
  el("send").textContent = "Sending…";
  el("status").textContent = "Classifying your response, selecting the branch, and preparing audio…";
  try {
    const data = await submitTurn(sessionId, text, "text");
    renderTurn(data);
    el("status").textContent = dialogueWarning(data)
      || (completed ? "Exercise complete. Review the evidence and timeline, or start again to try another response." : "Your turn. Notice how the caller's tactic changed.");
    await playResponse(el("audio"), el("audio-status"), data.audio_url);
  } catch (error) {
    el("status").textContent = error.message || "Unable to reach the backend. Your response has been kept.";
  } finally {
    el("send").textContent = "Send response";
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
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.continuous = false;
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

voiceCall = new VoiceCallController({
  audio: el("audio"),
  audioStatus: el("audio-status"),
  callStatus: el("call-status"),
  meta: el("call-meta"),
  interim: el("voice-interim"),
  confirmed: el("voice-confirmed"),
  support: el("voice-support"),
  replay: el("voice-replay"),
  continue: el("voice-continue"),
  pause: el("voice-pause"),
  end: el("voice-end"),
}, {
  onSession: (data) => {
    renderSession(data);
    el("voice-call").hidden = false;
    el("start-voice").textContent = "Restart voice call";
  },
  onTurn: (data) => renderTurn(data),
  onStateChange: (state, meta) => {
    if (!voiceMode) return;
    const processing = ["starting", "requesting_microphone", "submitting", "processing"].includes(state);
    setBusy(processing);
    el("status").textContent = meta.message;
    if (state === "terminal") {
      completed = true;
      el("status").textContent = "Exercise complete. Review the evidence and timeline, or restart with another fictional response.";
    }
    if (state === "error") setBusy(false);
  },
  onSupport: (text) => { el("voice-support").textContent = text; },
  onTextFallback: () => {
    setBusy(false);
    el("status").textContent = "Voice input is unavailable. Type a fictional response below to continue.";
    el("participant-text").focus();
  },
  onError: (error) => {
    el("status").textContent = error?.message || "The fictional call hit a temporary problem. Use typed mode to continue.";
    setBusy(false);
  },
});

el("start-voice").addEventListener("click", () => {
  clearExperience("Starting a fictional voice call…");
  voiceMode = true;
  el("voice-call").hidden = false;
  setBusy(true);
  void voiceCall.start(el("scenario").value);
});
el("voice-replay").addEventListener("click", () => { void voiceCall.replay(); });
el("voice-continue").addEventListener("click", () => { void voiceCall.continueAfterPlayback(); });
el("voice-pause").addEventListener("click", () => voiceCall.state === "paused" ? voiceCall.resume() : voiceCall.pause());
el("voice-end").addEventListener("click", () => { void voiceCall.endCall(); });
el("voice-text-fallback").addEventListener("click", () => voiceCall.enableTextFallback("Typed fallback selected. The fictional call will continue without speech recognition."));
el("audio").addEventListener("error", () => { el("audio-status").textContent = "Audio could not be loaded. Continue with the fictional transcript."; });

loadScenarios();
