import { createSession, endCall, getEvaluation, listScenarios, retryDialogue, submitTurn } from "./api.js";
import { playResponse, stopAudio } from "./audio.js";
import { VoiceCallController } from "./voice.js";

const el = (id) => document.getElementById(id);
const recognitionType = window.SpeechRecognition || window.webkitSpeechRecognition;
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
let retryAvailable = false;
let voiceCall;
let evaluationPollGeneration = 0;
let evaluationTimer = null;

function showScreen(name) {
  const title = el("screen-title");
  const cases = el("screen-cases");
  const home = el("screen-home");
  const call = el("screen-call");
  const score = el("screen-score");
  const debrief = el("debrief");
  const voiceCallEl = el("voice-call");

  if (title) title.hidden = name !== "title";
  if (cases) cases.hidden = !(name === "cases" || name === "home");
  if (home) home.hidden = !(name === "cases" || name === "home");
  if (call) call.hidden = name !== "call";
  if (score) score.hidden = name !== "score";

  if (name === "call") {
    if (voiceCallEl) voiceCallEl.hidden = false;
    if (debrief) debrief.hidden = true;
  } else if (name === "score") {
    if (debrief) debrief.hidden = false;
  } else {
    if (debrief) debrief.hidden = true;
    if (voiceCallEl) voiceCallEl.hidden = true;
  }
}

function callIsLocked() {
  if (!voiceMode || !voiceCall?.active) return false;
  return !["idle", "terminal", "error"].includes(voiceCall.state);
}

function setBusy(value) {
  busy = value;
  const locked = callIsLocked();
  const voiceStarting = voiceMode && voiceCall?.state === "idle" && !sessionId;
  const typedFallback = voiceMode && voiceCall?.typedFallback;
  if (el("start")) el("start").disabled = busy || voiceStarting || !catalogReady || locked;
  if (el("start-voice")) el("start-voice").disabled = busy || voiceStarting || !catalogReady || locked;
  if (el("scenario")) el("scenario").disabled = busy || voiceStarting || !catalogReady || locked;
  if (el("another-scenario")) el("another-scenario").disabled = busy || locked;
  const dialogueUnavailable = voiceMode && voiceCall?.state === "dialogue_unavailable";
  const typedDialogueUnavailable = !voiceMode && retryAvailable;
  const disabled = busy || !sessionId || completed || dialogueUnavailable || typedDialogueUnavailable || (voiceMode && !typedFallback);
  if (el("send")) el("send").disabled = disabled || listening;
  if (el("participant-text")) el("participant-text").disabled = disabled;
  if (el("microphone")) el("microphone").disabled = disabled || !recognitionType || voiceMode;
  if (el("text-end")) {
    el("text-end").disabled = busy || !sessionId || completed || (voiceMode && !typedFallback);
    el("text-end").hidden = !sessionId || voiceMode;
  }
  if (el("text-retry")) {
    el("text-retry").disabled = busy || !sessionId || completed || !retryAvailable;
    el("text-retry").hidden = voiceMode || !sessionId || completed || !retryAvailable;
  }
  if (el("turn-form")) el("turn-form").setAttribute("aria-busy", String(busy));
}

function selectedScenarioDescription() {
  const currentVal = el("scenario")?.value;
  const scenario = scenarios.find((item) => item.id === currentVal);
  
  if (scenario) {
    if (el("scenario-description")) el("scenario-description").textContent = `${scenario.description} Suspect entity: ${scenario.fictional_organization}.`;
    if (el("selected-scenario")) el("selected-scenario").textContent = `CASE DOSSIER: ${scenario.display_name.toUpperCase()}`;
    if (el("suspect-org-title")) el("suspect-org-title").textContent = scenario.display_name.toUpperCase();
    if (el("suspect-alias-text")) el("suspect-alias-text").textContent = `Target: ${scenario.fictional_organization}`;
  } else {
    if (el("scenario-description")) el("scenario-description").textContent = "The default investigation dossier is available. Review the case file before proceeding.";
    if (el("selected-scenario")) el("selected-scenario").textContent = "CASE DOSSIER: FICTIONAL BANK FRAUD";
  }

  // Synchronize active class on dynamic case cards
  document.querySelectorAll(".case-card").forEach((card) => {
    if (card.dataset.id === currentVal) {
      card.classList.add("active");
    } else {
      card.classList.remove("active");
    }
  });
}

function renderCaseCards() {
  const grid = el("case-dossier-grid");
  if (!grid) return;
  grid.replaceChildren();

  const caseTypeTitles = {
    fictional_bank_fraud_v1: "BANK WIRE HEIST",
    fictional_job_recruiter_v1: "RECRUITER HONEYTRAP",
    fictional_technical_support_v1: "TECH DIAGNOSTIC BREACH",
  };

  const caseStamps = {
    fictional_bank_fraud_v1: "CONFIDENTIAL / HEIST",
    fictional_job_recruiter_v1: "URGENT / HONEYTRAP",
    fictional_technical_support_v1: "PRIORITY / BREACH",
  };

  const caseTactics = {
    fictional_bank_fraud_v1: "Urgency Escalation · Account Lockdown Threats",
    fictional_job_recruiter_v1: "Authority Coercion · Upfront Fee Demands",
    fictional_technical_support_v1: "Fear Appeals · Remote Access Infiltration",
  };

  scenarios.forEach((scenario, index) => {
    const card = document.createElement("div");
    card.className = `case-card${scenario.id === el("scenario")?.value ? " active" : ""}`;
    card.dataset.id = scenario.id;
    card.tabIndex = 0;
    card.setAttribute("role", "radio");
    card.setAttribute("aria-checked", String(scenario.id === el("scenario")?.value));

    // Header with folder tab and stamp badge
    const header = document.createElement("div");
    header.className = "case-card-header";

    const tab = document.createElement("span");
    tab.className = "case-folder-tab";
    tab.textContent = `CASE #0${index + 1}`;

    const stamp = document.createElement("span");
    stamp.className = "case-stamp-badge";
    stamp.textContent = caseStamps[scenario.id] || "CONFIDENTIAL";

    header.append(tab, stamp);

    // Title
    const title = document.createElement("h3");
    title.className = "case-title";
    title.textContent = caseTypeTitles[scenario.id] || scenario.display_name.toUpperCase();

    // Target Organization
    const org = document.createElement("div");
    org.className = "case-org-line";
    org.innerHTML = `<span>🏛️</span><span>Target: ${scenario.fictional_organization}</span>`;

    // Scenario description
    const desc = document.createElement("p");
    desc.className = "case-desc";
    desc.textContent = scenario.description;

    // Tactical warning
    const tactics = document.createElement("div");
    tactics.className = "case-tactics-tag";
    tactics.textContent = `⚠️ ${caseTactics[scenario.id] || "Social Engineering Pretext"}`;

    // Safer guidelines
    const guidanceBox = document.createElement("div");
    guidanceBox.className = "case-guidance-box";
    const guidanceTitle = document.createElement("span");
    guidanceTitle.className = "guidance-title";
    guidanceTitle.textContent = "DETECTIVE PROTOCOL:";
    const guidanceList = document.createElement("ul");
    guidanceList.className = "guidance-list";
    (scenario.safer_response_guidance || []).slice(0, 2).forEach((rule) => {
      const li = document.createElement("li");
      li.className = "guidance-item";
      li.textContent = rule;
      guidanceList.append(li);
    });
    guidanceBox.append(guidanceTitle, guidanceList);

    card.append(header, title, org, desc, tactics, guidanceBox);

    const selectCase = () => {
      if (el("scenario")) {
        el("scenario").value = scenario.id;
        el("scenario").dispatchEvent(new Event("change"));
      }
    };

    card.addEventListener("click", selectCase);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selectCase();
      }
    });

    grid.append(card);
  });

  const counter = el("case-counter");
  if (counter) counter.textContent = `${scenarios.length} ACTIVE DOSSIERS`;
}

async function loadScenarios() {
  try {
    scenarios = await listScenarios();
    if (el("scenario")) {
      el("scenario").replaceChildren();
      for (const scenario of scenarios) {
        const option = document.createElement("option");
        option.value = scenario.id;
        option.textContent = scenario.display_name;
        el("scenario").append(option);
      }
    }
    if (!scenarios.length) throw new Error("No scenarios available");
  } catch {
    if (el("scenario")) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "Fictional bank fraud (default)";
      el("scenario").replaceChildren(option);
    }
    if (el("status")) el("status").textContent = "Case catalog unavailable. You can still investigate the default case.";
  } finally {
    catalogReady = true;
    renderCaseCards();
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
  retryAvailable = false;
  scenarioName = "Fictional bank fraud";
  showScreen("cases");
  if (el("selected-scenario")) el("selected-scenario").textContent = "No active investigation";
  if (el("debrief-outcome")) el("debrief-outcome").textContent = "";
  if (el("debrief-summary")) el("debrief-summary").textContent = "";
  if (el("debrief-tactics")) el("debrief-tactics").textContent = "";
  if (el("debrief-risk")) el("debrief-risk").textContent = "";
  if (el("debrief-boundaries")) el("debrief-boundaries").replaceChildren();
  if (el("debrief-verification")) el("debrief-verification").textContent = "";
  if (el("debrief-evidence")) el("debrief-evidence").replaceChildren();
  if (el("debrief-guidance")) el("debrief-guidance").replaceChildren();
  renderEvaluation(null);
  if (el("transcript")) el("transcript").replaceChildren(emptyMessage("Select a case dossier and initiate surveillance. Your interrogation choices dictate the outcome."));
  const firstDecision = document.createElement("li");
  firstDecision.textContent = "No decisions logged yet";
  if (el("timeline")) el("timeline").replaceChildren(firstDecision);
  if (el("participant-text")) el("participant-text").value = "";
  if (el("intent")) el("intent").textContent = "—";
  if (el("evidence")) el("evidence").textContent = "—";
  if (el("tactics")) el("tactics").textContent = "—";
  if (el("providers")) el("providers").textContent = "Waiting for connection";
  if (el("audio-status")) el("audio-status").textContent = "Audio appears here when available.";
  if (el("voice-support")) el("voice-support").textContent = "Speech recognition is checked when the call starts.";
  if (el("start")) el("start").textContent = "TEXT INTERROGATION";
  if (el("start-voice")) el("start-voice").textContent = "TAP THE WIRETAP CALL";
  if (el("send")) el("send").textContent = "SEND";
  if (el("text-end")) el("text-end").hidden = true;
  if (el("status")) el("status").textContent = statusText;
  if (el("scammer-text-content")) el("scammer-text-content").textContent = '"Connecting caller audio stream…"';
  if (el("live-suspect-bubble")) el("live-suspect-bubble").textContent = '"Connecting wiretap intercept... standby for audio incoming from target frequency."';
  stageUpdate("Not started", 0);
}

function message(speaker, text) {
  if (el("transcript")) {
    el("transcript").querySelector(".empty")?.remove();
    const article = document.createElement("article");
    article.className = speaker === "You" ? "transcript-bubble participant" : "transcript-bubble caller";
    const title = document.createElement("strong");
    title.textContent = speaker === "You" ? "DETECTIVE: " : "SUSPECT: ";
    const paragraph = document.createElement("span");
    paragraph.textContent = text;
    article.append(title, paragraph);
    el("transcript").append(article);
    article.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  if (speaker !== "You") {
    if (el("live-suspect-bubble")) el("live-suspect-bubble").textContent = `"${text}"`;
    if (el("scammer-text-content")) el("scammer-text-content").textContent = `"${text}"`;
  }
}

function stageUpdate(stage, risk = 0) {
  if (el("stage")) el("stage").textContent = label(stage);
  if (el("risk")) el("risk").value = risk;
  const pct = `${Math.round(risk * 100)}%`;
  if (el("risk-value")) el("risk-value").textContent = pct;
  if (el("threat-level-value")) el("threat-level-value").textContent = `${pct} · ${label(stage).toUpperCase()}`;
  if (el("threat-bar-fill")) el("threat-bar-fill").style.width = pct;
  if (el("threat-indicator-desc")) {
    if (risk > 0.6) el("threat-indicator-desc").textContent = "⚠️ Critical psychological coercion underway!";
    else if (risk > 0.3) el("threat-indicator-desc").textContent = "Suspect escalating urgency and pressure tactics";
    else el("threat-indicator-desc").textContent = "Suspect establishing authority and pretense";
  }
}

function timeline(text) {
  if (el("timeline")) {
    const item = document.createElement("li");
    item.textContent = text;
    el("timeline").append(item);
  }
}

function stopListening() {
  recognition?.abort();
  recognition = null;
  listening = false;
  if (el("microphone")) {
    el("microphone").classList.remove("recording");
    el("microphone").title = "Push-to-Talk Detective Radio Microphone";
  }
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
    ollama: "Ollama (qwen3:4b)",
    ollama_unavailable: "Ollama unavailable",
    ollama_timeout: "Ollama timeout",
    ollama_invalid_output: "Ollama invalid output",
    gemini: "Gemini 3.7",
    authored_fallback: "authored fallback",
  };
  const dialogue = dialogueLabels[data.dialogue_provider]
    || (data.dialogue_fallback ? "authored fallback" : (data.dialogue_provider || "unknown"));
  return `Safety policy: ${classifier} · Caller dialogue: ${dialogue} · Voice: ${voice} · Evaluator: Nemotron`;
}

function dialogueWarning(data) {
  return /^ollama_(?:unavailable|timeout|invalid_output)$/.test(String(data?.dialogue_provider || ""))
    ? "Suspect connection interrupted. Press Retry caller response to re-engage."
    : "";
}

function cancelEvaluationPolling() {
  evaluationPollGeneration += 1;
  if (evaluationTimer) window.clearTimeout(evaluationTimer);
  evaluationTimer = null;
}

function renderEvaluation(data) {
  const card = el("evaluation-card");
  if (!card) return;
  if (!data?.status) {
    card.hidden = true;
    if (el("evaluation-status")) el("evaluation-status").textContent = "";
    if (el("evaluation-summary")) el("evaluation-summary").textContent = "";
    if (el("evaluation-safety")) el("evaluation-safety").textContent = "";
    if (el("evaluation-tactics")) el("evaluation-tactics").textContent = "";
    if (el("evaluation-risk")) el("evaluation-risk").textContent = "";
    if (el("evaluation-confidence")) el("evaluation-confidence").textContent = "";
    if (el("evaluation-evidence")) el("evaluation-evidence").replaceChildren();
    return;
  }
  card.hidden = false;
  const provider = data.provider === "nemotron" ? "NVIDIA Nemotron" : "deterministic fallback";
  if (data.status === "pending") {
    if (el("evaluation-status")) el("evaluation-status").textContent = `Forensic Evaluation: Pending review (${provider})…`;
    if (el("evaluation-summary")) el("evaluation-summary").textContent = "Independent analysis analyzing suspect tape.";
    return;
  }
  if (data.status === "failed") {
    if (el("evaluation-status")) el("evaluation-status").textContent = `Forensic Evaluation: Diagnostic logged (${provider})`;
    if (el("evaluation-summary")) el("evaluation-summary").textContent = data.summary || "Forensic analysis completed with standard model.";
    return;
  }
  if (el("evaluation-status")) el("evaluation-status").textContent = `Forensic Evaluation: Complete (${provider})`;
  if (el("evaluation-summary")) el("evaluation-summary").textContent = data.summary || "Case debrief secured.";
  if (el("evaluation-safety")) el("evaluation-safety").textContent = `Safety assessment: ${label(data.safety_assessment || "unknown")}`;
  const tactics = data.observed_tactics || [];
  if (el("evaluation-tactics")) el("evaluation-tactics").textContent = tactics.length ? `Tactics identified: ${tactics.map(label).join(", ")}` : "";
  if (el("evaluation-risk") && data.recommended_risk_band) {
    el("evaluation-risk").textContent = `Recommended threat band: ${label(data.recommended_risk_band)}`;
  }
  if (el("evaluation-confidence") && data.confidence !== undefined) {
    el("evaluation-confidence").textContent = `Confidence score: ${Math.round(data.confidence * 100)}%`;
  }
  if (el("evaluation-evidence")) {
    el("evaluation-evidence").replaceChildren();
    for (const item of data.evidence || []) {
      const li = document.createElement("li");
      li.textContent = item;
      el("evaluation-evidence").append(li);
    }
  }
}

function pollEvaluation(currentSessionId, generation) {
  const delays = [1500, 2500, 4000];
  let attempt = 0;
  const poll = async () => {
    if (generation !== evaluationPollGeneration || currentSessionId !== sessionId) return;
    try {
      const evaluation = await getEvaluation(currentSessionId);
      if (generation !== evaluationPollGeneration || currentSessionId !== sessionId) return;
      renderEvaluation(evaluation);
      if (evaluation.status !== "pending") return;
    } catch {
      // Continue polling silently
    }
    attempt += 1;
    if (attempt < delays.length) {
      evaluationTimer = window.setTimeout(poll, delays[attempt]);
    }
  };
  evaluationTimer = window.setTimeout(poll, delays[0]);
}

function callerNameFromScenario(id) {
  const map = {
    fictional_bank_fraud_v1: "Lumenvale Demo Credit Union",
    fictional_job_recruiter_v1: "Fernwick Demo Careers",
    fictional_technical_support_v1: "Cobalt Finch Demo Support",
  };
  return map[id] || "Unknown Suspect Organization";
}

function renderCallerIdentity(scenarioId) {
  const callerName = callerNameFromScenario(scenarioId);
  if (el("suspect-org-title")) el("suspect-org-title").textContent = callerName;
  if (el("suspect-alias-text")) el("suspect-alias-text").textContent = `Target: ${callerName}`;
  const initials = callerName.split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase() || "SC";
  if (el("suspect-avatar-initials")) el("suspect-avatar-initials").textContent = initials;
  if (el("caller-avatar")) el("caller-avatar").textContent = initials;
}

function renderDebrief(data) {
  const debrief = data.debrief;
  if (!debrief) return;
  showScreen("score");
  if (el("debrief-heading")) el("debrief-heading").textContent = `${debrief.scenario_name || scenarioName} — Case Closed`;
  if (el("debrief-outcome")) el("debrief-outcome").textContent = label(debrief.outcome || data.stage_after).toUpperCase();
  if (el("debrief-summary")) el("debrief-summary").textContent = debrief.summary || data.scammer_text;
  const tactics = debrief.tactics_observed || [];
  if (el("debrief-tactics")) el("debrief-tactics").textContent = tactics.length ? `Tactics identified: ${tactics.map(label).join(", ")}` : "";
  const riskPercent = Math.round((debrief.training_risk_score ?? 0) * 100);
  if (el("debrief-risk")) el("debrief-risk").textContent = `Deception vulnerability: ${riskPercent}%`;

  if (el("metric-final-risk")) {
    el("metric-final-risk").textContent = riskPercent > 60 ? "HIGH" : (riskPercent > 30 ? "MEDIUM" : "LOW");
  }
  if (el("metric-boundaries-count")) {
    el("metric-boundaries-count").textContent = String(debrief.boundaries_set?.length || 0);
  }
  if (el("metric-pressure-grade")) {
    el("metric-pressure-grade").textContent = `${Math.max(10, 100 - riskPercent)}%`;
  }

  if (el("debrief-boundaries")) {
    el("debrief-boundaries").replaceChildren();
    for (const boundary of debrief.boundaries_set || []) {
      const item = document.createElement("li");
      item.textContent = boundary;
      el("debrief-boundaries").append(item);
    }
  }

  if (el("debrief-verification")) {
    el("debrief-verification").textContent = debrief.verification_requested
      ? "Verified · Detective requested independent verification through official bureau channels."
      : "Unverified · No independent verification protocol was initiated.";
  }

  if (el("debrief-evidence")) {
    el("debrief-evidence").replaceChildren();
    for (const evidence of debrief.evidence || []) {
      const item = document.createElement("li");
      item.textContent = evidence;
      el("debrief-evidence").append(item);
    }
  }

  if (el("debrief-guidance")) {
    el("debrief-guidance").replaceChildren();
    const guidance = debrief.safer_response_guidance || ["Terminate unexpected inquiries and verify through trusted official channels."];
    for (const advice of Array.isArray(guidance) ? guidance : [guidance]) {
      const item = document.createElement("li");
      item.textContent = advice;
      el("debrief-guidance").append(item);
    }
  }

  // Calculate Detective 5-Star Rank
  let stars = 5;
  let rankTitle = "CHIEF INSPECTOR";
  let rankSub = "METROPOLITAN CYBER FRAUD SPECIALIST";
  if (riskPercent > 70) {
    stars = 1;
    rankTitle = "ROOKIE ON PROBATION";
    rankSub = "CRITICAL PROTOCOL COMPROMISE";
  } else if (riskPercent > 45) {
    stars = 2;
    rankTitle = "JUNIOR INVESTIGATOR";
    rankSub = "VULNERABLE TO SOCIAL ENGINEERING";
  } else if (riskPercent > 25) {
    stars = 3;
    rankTitle = "FIELD INVESTIGATOR";
    rankSub = "ADEQUATE BOUNDARIES DEFENDED";
  } else if (debrief.boundaries_set?.length) {
    stars = 5;
    rankTitle = "CHIEF INSPECTOR";
    rankSub = "IMPECCABLE BOUNDARY DEFENSE";
  } else {
    stars = 4;
    rankTitle = "SENIOR DETECTIVE";
    rankSub = "EXCELLENT DECEPTION AVOIDANCE";
  }

  if (el("detective-rank-title")) el("detective-rank-title").textContent = rankTitle;
  if (el("detective-rank-sub")) el("detective-rank-sub").textContent = rankSub;

  if (el("detective-stars")) {
    el("detective-stars").replaceChildren();
    for (let i = 0; i < 5; i++) {
      const span = document.createElement("span");
      span.className = i < stars ? "star-gold" : "star-dim";
      span.textContent = "★";
      el("detective-stars").append(span);
    }
  }

  const stamp = el("debrief-outcome");
  if (stamp) {
    if (stars >= 3) {
      stamp.style.color = "var(--accent-emerald)";
      stamp.textContent = "FRAUD PREVENTED";
    } else {
      stamp.style.color = "var(--accent-crimson)";
      stamp.textContent = "COMPROMISED";
    }
  }

  if (data.evaluation) renderEvaluation(data.evaluation);
  else pollEvaluation(sessionId, evaluationPollGeneration);
}

function renderSession(data) {
  sessionId = data.session_id;
  scenarioName = data.scenario_name;
  retryAvailable = Boolean(data.retry_available);
  completed = Boolean(data.completed);
  showScreen("call");
  renderCallerIdentity(data.scenario_id);
  if (el("selected-scenario")) el("selected-scenario").textContent = `ACTIVE WIRETAP: ${scenarioName.toUpperCase()}`;
  stageUpdate(data.stage, data.risk_score);
  if (el("tactics")) el("tactics").textContent = (data.tactics_triggered || []).map(label).join(", ") || "—";
  if (el("providers")) el("providers").textContent = providerSummary(data);

  if (data.scammer_text) {
    message("Simulated caller", data.scammer_text);
    if (el("scammer-text-content")) el("scammer-text-content").textContent = `"${data.scammer_text}"`;
  }

  if (data.retry_available) {
    if (el("voice-support")) el("voice-support").textContent = dialogueWarning(data) || "Suspect line unavailable. Press Retry line.";
    timeline("Opening line pending · retry available");
  }
  if (el("status")) el("status").textContent = data.call_active === false ? "Wiretap terminated" : "Surveillance active · your turn when suspect finishes.";
  setBusy(false);
}

function renderTurn(data) {
  message("You", data.participant_text);
  if (data.scammer_text) {
    message("Simulated caller", data.scammer_text);
    if (el("scammer-text-content")) el("scammer-text-content").textContent = `"${data.scammer_text}"`;
  }
  completed = Boolean(data.completed);
  retryAvailable = Boolean(data.retry_available);
  stageUpdate(data.stage_after, data.risk_score);
  if (el("tactics")) el("tactics").textContent = (data.tactics_triggered || []).map(label).join(", ") || "—";
  if (el("intent")) el("intent").textContent = `${label(data.analysis.participant_intent)} · ${Math.round(data.analysis.confidence * 100)}% confidence`;
  if (el("evidence")) el("evidence").textContent = data.analysis.evidence_span;
  if (el("providers")) el("providers").textContent = providerSummary(data);
  const warning = dialogueWarning(data);
  if (warning && el("voice-support")) el("voice-support").textContent = warning;
  timeline(`${label(data.stage_before)} → ${label(data.stage_after)} · ${label(data.analysis.participant_intent)} · tactics: ${(data.tactics_triggered || []).map(label).join(", ") || "none"} · risk ${Math.round((data.risk_before ?? 0) * 100)}% → ${Math.round(data.risk_score * 100)}% · ${Math.round(data.analysis.confidence * 100)}% confidence · evidence: “${data.analysis.evidence_span}”`);
  if (data.retry_available && el("voice-support")) el("voice-support").textContent = dialogueWarning(data);
  if (el("participant-text")) el("participant-text").value = "";
}

function renderEnded(data) {
  completed = true;
  retryAvailable = false;
  stageUpdate(data.stage, data.risk_score);
  if (el("status")) el("status").textContent = "Wiretap terminated · reviewing case file.";
  if (el("providers") && (!el("providers").textContent || el("providers").textContent === "Waiting for connection")) {
    el("providers").textContent = "Safety policy: fast_safety_policy · Caller dialogue: Ollama · Voice: provider status shown above";
  }
  timeline("Call ended safely by participant · deterministic debrief created");
  renderDebrief(data);
  setBusy(false);
}

// Navigation event bindings
el("play-now-btn")?.addEventListener("click", () => {
  showScreen("cases");
});

el("btn-back-title")?.addEventListener("click", () => {
  showScreen("title");
});

el("scenario")?.addEventListener("change", () => {
  selectedScenarioDescription();
  if (sessionId || completed) {
    clearExperience("Case file changed. Start the investigation when ready.");
    setBusy(false);
  }
});

el("another-scenario")?.addEventListener("click", () => {
  clearExperience("Select your next case dossier above, then initiate surveillance.");
  setBusy(false);
  showScreen("cases");
  el("scenario")?.focus();
});

el("start")?.addEventListener("click", async () => {
  clearExperience("Initiating silent text interrogation terminal…");
  voiceMode = false;
  showScreen("call");
  setBusy(true);
  try {
    const data = await createSession(el("scenario")?.value);
    renderSession(data);
    timeline(`Investigation started · Scenario: ${scenarioName} · Mode: text interrogation`);
    if (data.audio_url) await playResponse(el("audio"), data.audio_url);
  } catch (error) {
    if (el("status")) el("status").textContent = error?.message || "Could not connect to surveillance wiretap.";
  } finally {
    setBusy(false);
  }
});

el("turn-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const textInput = el("participant-text");
  const text = textInput?.value.trim();
  if (!text || busy || !sessionId) return;
  setBusy(true);
  try {
    const data = await submitTurn(sessionId, text, "text");
    renderTurn(data);
    if (data.audio_url) await playResponse(el("audio"), data.audio_url);
    if (data.completed) {
      renderEnded(data);
    } else {
      textInput?.focus();
    }
  } catch (error) {
    if (el("status")) el("status").textContent = error?.message || "Interrogation line transmission error.";
  } finally {
    setBusy(false);
  }
});

el("text-end")?.addEventListener("click", async () => {
  if (!sessionId || busy) return;
  setBusy(true);
  try {
    const data = await endCall(sessionId);
    renderEnded(data);
  } catch (error) {
    if (el("status")) el("status").textContent = error?.message || "Could not safely exit wiretap.";
  } finally {
    setBusy(false);
  }
});

el("text-retry")?.addEventListener("click", async () => {
  if (!sessionId || busy || !retryAvailable) return;
  setBusy(true);
  try {
    const data = await retryDialogue(sessionId);
    retryAvailable = Boolean(data.retry_available);
    if ("stage_after" in data) renderTurn(data);
    else renderSession(data);
    if (data.audio_url) await playResponse(el("audio"), data.audio_url);
  } catch (error) {
    if (el("status")) el("status").textContent = error?.message || "Could not retry caller response.";
  } finally {
    setBusy(false);
  }
});

// Tactical Interrogation Response Chips
document.querySelectorAll(".tactic-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    const text = chip.dataset.text;
    const input = el("participant-text");
    if (text && input) {
      input.value = text;
      input.focus();
    }
  });
});

// Push-to-talk Detective Radio Microphone
if (el("microphone")) {
  el("microphone").addEventListener("click", () => {
    if (listening) {
      stopListening();
      if (el("status")) el("status").textContent = "Detective radio transmitted. Ready to send.";
      return;
    }
    if (!recognitionType) {
      if (el("status")) el("status").textContent = "Detective radio speech transcription unavailable in this browser. Please type.";
      return;
    }
    recognition = new recognitionType();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      if (el("participant-text")) el("participant-text").value = transcript;
      stopListening();
      if (el("status")) el("status").textContent = "Statement captured by radio. Ready to interrogate.";
      setBusy(busy);
    };
    recognition.onerror = () => {
      stopListening();
      if (el("status")) el("status").textContent = "Radio signal interference. Please type statement.";
      setBusy(busy);
    };
    recognition.onend = () => {
      stopListening();
      setBusy(busy);
    };
    try {
      recognition.start();
      listening = true;
      el("microphone").classList.add("recording");
      el("microphone").title = "Radio channel active · speak statement…";
      if (el("status")) el("status").textContent = "Radio channel open. Speak your interrogation statement…";
      setBusy(busy);
    } catch {
      stopListening();
      if (el("status")) el("status").textContent = "Could not activate radio channel. Type your statement.";
    }
  });
}

// Voice Call Controller for Full Audio Wiretap
voiceCall = new VoiceCallController({
  audio: el("audio"),
  audioStatus: el("audio-status"),
  callStatus: el("call-status"),
  meta: el("call-meta-value"),
  interim: el("voice-interim"),
  confirmed: el("voice-confirmed"),
  support: el("voice-support"),
  replay: el("voice-replay"),
  continue: el("voice-continue"),
  pause: el("voice-pause"),
  end: el("voice-end"),
  retry: el("voice-retry"),
}, {
  onSession: (data) => {
    renderSession(data);
    if (el("voice-call")) el("voice-call").hidden = false;
    if (el("start-voice")) el("start-voice").textContent = "RE-TAP WIRETAP CALL";
  },
  onTurn: (data) => renderTurn(data),
  onRetry: (data) => {
    renderSession(data);
    if (el("voice-call")) el("voice-call").hidden = false;
  },
  onEnded: (data) => renderEnded(data),
  onStateChange: (state, meta) => {
    if (!voiceMode) return;
    const processing = ["starting", "requesting_microphone", "submitting", "processing"].includes(state);
    setBusy(processing);
    if (el("status")) el("status").textContent = meta.message;
    if (state === "terminal") {
      completed = true;
      if (el("status")) el("status").textContent = "Wiretap terminated · reviewing case file.";
      setBusy(false);
    }
    if (state === "dialogue_unavailable") setBusy(false);
    if (state === "error") setBusy(false);
  },
  onSupport: (text) => { if (el("voice-support")) el("voice-support").textContent = text; },
  onTextFallback: () => {
    setBusy(false);
    if (el("status")) el("status").textContent = "Voice input unavailable. Type your interrogation statement below.";
    el("participant-text")?.focus();
  },
  onError: (error) => {
    if (el("status")) el("status").textContent = error?.message || "Wiretap connection hit an issue. Use typed mode to proceed.";
    setBusy(false);
  },
});

el("start-voice")?.addEventListener("click", () => {
  clearExperience("Initiating police wiretap surveillance…");
  voiceMode = true;
  showScreen("call");
  setBusy(true);
  void voiceCall.start(el("scenario")?.value);
});

el("voice-replay")?.addEventListener("click", () => { void voiceCall.replay(); });
el("voice-continue")?.addEventListener("click", () => { void voiceCall.continueAfterPlayback(); });
el("voice-pause")?.addEventListener("click", () => voiceCall.state === "paused" ? voiceCall.resume() : voiceCall.pause());
el("voice-end")?.addEventListener("click", () => { void voiceCall.endCall(); });
el("voice-retry")?.addEventListener("click", () => { void voiceCall.retryCaller(); });
el("voice-text-fallback")?.addEventListener("click", () => voiceCall.enableTextFallback("Text fallback engaged. Wiretap proceeds with case notes."));

// Synchronize audio visualizer with live audio element
const audioEl = el("audio");
if (audioEl) {
  const setVisualizerActive = (active) => {
    const viz = el("audio-wave-visualizer");
    if (viz) {
      if (active) {
        viz.classList.add("playing");
        viz.classList.add("speaking");
      } else {
        viz.classList.remove("playing");
        viz.classList.remove("speaking");
      }
    }
  };

  audioEl.addEventListener("play", () => {
    setVisualizerActive(true);
    const l = el("audio-wave-label");
    if (l) l.textContent = "Wiretap Audio Active · ElevenLabs Stream";
  });
  audioEl.addEventListener("pause", () => {
    setVisualizerActive(false);
    const l = el("audio-wave-label");
    if (l) l.textContent = "Wiretap Audio Standby · Line Open";
  });
  audioEl.addEventListener("ended", () => {
    setVisualizerActive(false);
    const l = el("audio-wave-label");
    if (l) l.textContent = "Suspect Speech Finished · Awaiting Detective Response";
  });
  audioEl.addEventListener("error", () => {
    setVisualizerActive(false);
    if (el("audio-status")) el("audio-status").textContent = "Audio stream standby.";
  });
}

// Initial Screen: Display Title Screen with PLAY NOW button
showScreen("title");
loadScenarios();
