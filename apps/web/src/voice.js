import { createSession, endCall as requestEndCall, retryDialogue, submitTurn } from "./api.js";
import { playResponse, stopAudio } from "./audio.js";

export const VOICE_STATES = Object.freeze([
  "idle",
  "starting",
  "requesting_microphone",
  "caller_speaking",
  "listening",
  "transcribing",
  "submitting",
  "processing",
  "dialogue_unavailable",
  "paused",
  "terminal",
  "error",
  "text_fallback",
]);

const stateLabels = {
  idle: "Ready",
  starting: "Starting call",
  requesting_microphone: "Requesting microphone",
  caller_speaking: "Caller speaking",
  listening: "Your turn · listening",
  transcribing: "Transcribing your response",
  submitting: "Sending your response",
  processing: "Preparing the next caller response",
  dialogue_unavailable: "Caller dialogue unavailable · retry needed",
  paused: "Call paused",
  terminal: "Call ended",
  error: "Call error",
  text_fallback: "Text fallback",
};

const formatDuration = (seconds) => {
  const minutes = Math.floor(seconds / 60);
  const remainder = String(seconds % 60).padStart(2, "0");
  return `${minutes}:${remainder}`;
};

export class VoiceCallController {
  constructor(elements, callbacks = {}) {
    this.elements = elements;
    this.callbacks = callbacks;
    this.recognitionType = window.SpeechRecognition || window.webkitSpeechRecognition;
    this.state = "idle";
    this.generation = 0;
    this.active = false;
    this.sessionId = null;
    this.recognition = null;
    this.recognitionRunning = false;
    this.submissionInFlight = false;
    this.finalCaptured = false;
    this.silenceRetries = 0;
    this.typedFallback = false;
    this.currentAudioUrl = null;
    this.awaitingContinue = false;
    this.pausedFrom = null;
    this.turnCount = 0;
    this.startedAt = 0;
    this.timer = null;
    this.readDelay = null;
    this.setState("idle", "Voice call ready when you are.");
  }

  get supportsSpeech() {
    return Boolean(this.recognitionType);
  }

  _isCurrent(token) {
    return this.active && token === this.generation;
  }

  _meta() {
    const elapsed = this.startedAt ? Math.max(0, Math.floor((Date.now() - this.startedAt) / 1000)) : 0;
    return { turnCount: this.turnCount, elapsedSeconds: elapsed };
  }

  _updateMeta() {
    if (this.elements.meta) {
      const meta = this._meta();
      this.elements.meta.textContent = `Turn ${meta.turnCount} · ${formatDuration(meta.elapsedSeconds)}`;
    }
    this.callbacks.onMeta?.(this._meta());
  }

  setState(nextState, message = "") {
    if (!VOICE_STATES.includes(nextState)) return;
    this.state = nextState;
    if (this.elements.callStatus) {
      this.elements.callStatus.textContent = message || stateLabels[nextState];
      this.elements.callStatus.dataset.state = nextState;
    }
    if (this.elements.pause) {
      this.elements.pause.textContent = nextState === "paused" ? "Resume call" : "Pause call";
      this.elements.pause.disabled = !this.active || ["idle", "starting", "requesting_microphone", "submitting", "processing", "dialogue_unavailable", "terminal", "error", "text_fallback"].includes(nextState);
    }
    if (this.elements.end) {
      this.elements.end.disabled = !this.active || ["idle", "starting", "requesting_microphone", "submitting", "processing", "terminal"].includes(nextState);
    }
    if (this.elements.continue) {
      this.elements.continue.hidden = !["paused"].includes(nextState);
      this.elements.continue.disabled = !this.active || nextState !== "paused";
    }
    if (this.elements.retry) {
      this.elements.retry.hidden = nextState !== "dialogue_unavailable";
      this.elements.retry.disabled = !this.active || nextState !== "dialogue_unavailable";
    }
    this.callbacks.onStateChange?.(nextState, { message: message || stateLabels[nextState], ...this._meta(), typedFallback: this.typedFallback });
  }

  _setSupport(text) {
    if (this.elements.support) this.elements.support.textContent = text;
    this.callbacks.onSupport?.(text);
  }

  _setInterim(text) {
    if (this.elements.interim) this.elements.interim.textContent = text || "Listening for a fictional response…";
  }

  _setConfirmed(text) {
    if (this.elements.confirmed) this.elements.confirmed.textContent = text || "No response captured yet.";
  }

  _clearTimer() {
    if (this.timer) window.clearInterval(this.timer);
    this._clearReadDelay();
    this.timer = null;
  }

  _clearReadDelay() {
    if (this.readDelay) window.clearTimeout(this.readDelay);
    this.readDelay = null;
  }

  _startTimer() {
    this._clearTimer();
    this.timer = window.setInterval(() => this._updateMeta(), 1000);
    this._updateMeta();
  }

  _abortRecognition() {
    const current = this.recognition;
    this.recognition = null;
    this.recognitionRunning = false;
    if (current) {
      try { current.abort(); } catch { /* already stopped */ }
    }
  }

  reset() {
    this.generation += 1;
    this.active = false;
    this.sessionId = null;
    this.submissionInFlight = false;
    this.finalCaptured = false;
    this.silenceRetries = 0;
    this.typedFallback = false;
    this.currentAudioUrl = null;
    this.awaitingContinue = false;
    this.pausedFrom = null;
    this.turnCount = 0;
    this.startedAt = 0;
    this._clearTimer();
    this._abortRecognition();
    if (this.elements.audio) stopAudio(this.elements.audio);
    this._setInterim("");
    this._setConfirmed("");
    this._setSupport("");
    this.setState("idle", "Voice call ready when you are.");
  }

  async _requestMicrophone(token) {
    if (!this._isCurrent(token) || !this.recognitionType) return;
    if (!navigator.mediaDevices?.getUserMedia) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      if (this._isCurrent(token)) this._setSupport("Microphone permission granted. Only the final recognized transcript is sent to the simulation.");
    } catch {
      if (this._isCurrent(token)) this.enableTextFallback("Microphone permission was not granted. Voice input is paused; use the fictional typed fallback.");
    }
  }

  async start(scenarioId) {
    this.reset();
    const token = ++this.generation;
    this.active = true;
    this.startedAt = Date.now();
    this.setState("starting", "Starting a fictional voice call…");
    this._startTimer();
    try {
      const data = await createSession(scenarioId, "voice");
      if (!this._isCurrent(token)) return;
      this.sessionId = data.session_id;
      this.callbacks.onSession?.(data);
      if (data.retry_available || !data.scammer_text) {
        this.setState("dialogue_unavailable", "Caller dialogue is unavailable. Press Retry caller response.");
        this._setSupport("Ollama did not provide the caller line. The call is preserved; retry when ready.");
        return;
      }
      if (this.recognitionType) {
        this.setState("requesting_microphone", "Requesting microphone permission…");
        await this._requestMicrophone(token);
      } else {
        this.enableTextFallback("Voice input is unavailable in this browser. Use the fictional typed fallback below.");
      }
      if (!this._isCurrent(token)) return;
      await this.playCaller(data, token, !this.typedFallback);
    } catch (error) {
      if (!this._isCurrent(token)) return;
      this.setState("error", "The fictional call could not start. You can use text mode instead.");
      this.callbacks.onError?.(error);
    }
  }

  async playCaller(data, token = this.generation, autoListen = true) {
    if (!this._isCurrent(token)) return;
    if (data.scammer_text === "") {
      this.setState("dialogue_unavailable", "Caller dialogue is unavailable. Press Retry caller response.");
      return;
    }
    this._clearReadDelay();
    this.finalCaptured = false;
    this.currentAudioUrl = data.audio_url || null;
    this.awaitingContinue = false;
    this.silenceRetries = 0;
    if (!data.audio_url) {
      this._setSupport("Text-only caller response. No audio was stored; the simulation can continue with text.");
      if (this.typedFallback || !autoListen) {
        this.setState("text_fallback", "Voice audio is unavailable. Type a fictional response to continue.");
        return;
      }
      this.setState("caller_speaking", "Caller response is shown as text. Your turn will begin shortly…");
      this.readDelay = window.setTimeout(() => {
        if (this._isCurrent(token)) this.beginListening(token);
      }, 900);
      return;
    }
    this.setState("caller_speaking", "Caller speaking · synthetic audio");
    const ended = () => {
      if (!this._isCurrent(token)) return;
      if (autoListen && !this.typedFallback) this.beginListening(token);
      else this.setState("text_fallback", "Caller response finished. Type a fictional response to continue.");
    };
    const blocked = () => {
      if (!this._isCurrent(token)) return;
      this.awaitingContinue = true;
      this.pausedFrom = "caller_speaking";
      this.setState("paused", "Audio autoplay was blocked. Press Play caller response, or Continue to listening.");
    };
    const failed = () => {
      if (!this._isCurrent(token)) return;
      this.awaitingContinue = true;
      this.pausedFrom = "caller_speaking";
      this.setState("paused", "The caller audio could not be played. Read the transcript, then continue when ready.");
    };
    await playResponse(this.elements.audio, this.elements.audioStatus, data.audio_url, {
      onEnded: ended,
      onBlocked: blocked,
      onError: failed,
    });
    if (!this._isCurrent(token)) return;
    if (this.elements.replay) this.elements.replay.disabled = false;
  }

  async continueAfterPlayback() {
    if (!this.active || this.state !== "paused") return;
    const token = this.generation;
    this.awaitingContinue = false;
    if (this.pausedFrom === "caller_speaking" && this.currentAudioUrl && this.elements.audio?.src) {
      try {
        this.setState("caller_speaking", "Caller speaking · synthetic audio");
        await this.elements.audio.play();
        return;
      } catch { /* explicit continue below is the safe fallback */ }
    }
    if (this.typedFallback) {
      this.setState("text_fallback", "Text fallback is active. Type a fictional response to continue.");
      return;
    }
    this.beginListening(token);
  }

  beginListening(token = this.generation) {
    if (!this._isCurrent(token) || this.typedFallback || this.state === "terminal" || this.submissionInFlight) return;
    if (!this.recognitionType) {
      this.enableTextFallback("Voice input is unavailable in this browser. Use the fictional typed fallback below.");
      return;
    }
    this._clearReadDelay();
    this._abortRecognition();
    const recognition = new this.recognitionType();
    this.recognition = recognition;
    this.recognitionRunning = false;
    this.finalCaptured = false;
    let finalText = "";
    let interimText = "";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-US";
    recognition.onstart = () => {
      if (this._isCurrent(token) && this.recognition === recognition) {
        this.recognitionRunning = true;
        this.setState("listening", "Your turn · listening for a fictional response…");
      }
    };
    recognition.onresult = (event) => {
      if (!this._isCurrent(token) || this.recognition !== recognition || this.finalCaptured) return;
      interimText = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const transcript = result[0]?.transcript || "";
        if (result.isFinal) finalText += `${transcript} `;
        else interimText += transcript;
      }
      this._setInterim((finalText + interimText).trim());
      if (finalText.trim()) this._submitRecognized(finalText.trim(), token, recognition);
    };
    recognition.onerror = (event) => {
      if (!this._isCurrent(token) || this.recognition !== recognition) return;
      if (["not-allowed", "service-not-allowed", "audio-capture"].includes(event.error)) {
        this.enableTextFallback("Microphone or browser speech recognition is unavailable. Use the fictional typed fallback.");
      } else if (event.error !== "no-speech") {
        this._setSupport("Speech recognition had a temporary problem. You can try listening once more or switch to typing.");
      }
    };
    recognition.onend = () => {
      if (!this._isCurrent(token) || this.recognition !== recognition) return;
      this.recognitionRunning = false;
      this.recognition = null;
      if (!this.finalCaptured && !this.submissionInFlight && this.state === "listening") this._handleSilence(token);
    };
    try {
      this.setState("listening", "Your turn · listening for a fictional response…");
      recognition.start();
    } catch {
      this.enableTextFallback("The browser could not start speech recognition. Use the fictional typed fallback.");
    }
  }

  _handleSilence(token) {
    if (!this._isCurrent(token)) return;
    if (this.silenceRetries < 1) {
      this.silenceRetries += 1;
      this.setState("paused", "I didn’t catch that. Listening once more…");
      this.readDelay = window.setTimeout(() => this.beginListening(token), 500);
      return;
    }
    this.setState("paused", "I didn’t catch a fictional response. Press Resume call or switch to typing.");
  }

  _submitRecognized(text, token, recognition) {
    if (!this._isCurrent(token) || this.submissionInFlight || this.finalCaptured) return;
    this.finalCaptured = true;
    this._setConfirmed(text);
    this._setInterim(text);
    try { recognition.stop(); } catch { /* onend still settles the turn */ }
    void this._submitTranscript(text, "voice", token);
  }

  async _submitTranscript(text, inputMode, token = this.generation) {
    const cleaned = text.trim();
    if (!cleaned || !this._isCurrent(token) || this.submissionInFlight || !this.sessionId) return;
    this.submissionInFlight = true;
    this.setState("submitting", "Submitting the final transcript…");
    this.setState("processing", "Selecting the next fictional tactic…");
    try {
      const data = await submitTurn(this.sessionId, cleaned, inputMode);
      if (!this._isCurrent(token)) return;
      this.turnCount += 1;
      this.callbacks.onTurn?.(data);
      await this.playCaller(data, token, !this.typedFallback);
    } catch (error) {
      if (this._isCurrent(token)) {
        if (error.dialogueUnavailable) {
          this.setState("dialogue_unavailable", "Caller dialogue is unavailable. Press Retry caller response.");
          this._setSupport(error.message);
          this.callbacks.onDialogueUnavailable?.(error);
        } else {
          this.setState("error", "The response could not be submitted. Your fictional text was not sent again.");
        }
        this.callbacks.onError?.(error);
      }
    } finally {
      this.submissionInFlight = false;
    }
  }

  _enterTerminal() {
    this._abortRecognition();
    this._clearTimer();
    if (this.elements.audio) stopAudio(this.elements.audio);
    this.awaitingContinue = false;
    this.setState("terminal", "Call ended · review the debrief");
  }

  async submitTyped(text) {
    if (!this.active || !this.typedFallback || this.state === "terminal" || this.state === "dialogue_unavailable") return;
    await this._submitTranscript(text, "text", this.generation);
  }

  enableTextFallback(reason) {
    if (!this.active) return;
    this.typedFallback = true;
    this._abortRecognition();
    this._setSupport(`${reason} No raw microphone audio is stored by SCAMSTAGE; only a recognized transcript is sent.`);
    this.setState("text_fallback", reason);
    this.callbacks.onTextFallback?.(reason);
  }

  pause() {
    if (!this.active || this.state === "terminal") return;
    if (this.state === "listening") {
      this.pausedFrom = "listening";
      this._abortRecognition();
      this.setState("paused", "Call paused. Resume when you are ready to give a fictional response.");
    } else if (this.state === "caller_speaking") {
      this.pausedFrom = "caller_speaking";
      this.elements.audio?.pause();
      this.setState("paused", "Call paused. Resume to continue the fictional caller response.");
    }
  }

  resume() {
    if (!this.active || this.state !== "paused") return;
    if (this.pausedFrom === "caller_speaking") void this.continueAfterPlayback();
    else if (this.typedFallback) this.setState("text_fallback", "Text fallback is active. Type a fictional response to continue.");
    else this.beginListening(this.generation);
  }

  async replay() {
    if (!this.active || !this.currentAudioUrl || this.state === "terminal") return;
    const token = this.generation;
    this._abortRecognition();
    await this.playCaller({ audio_url: this.currentAudioUrl }, token, !this.typedFallback);
  }

  async retryCaller() {
    if (!this.active || this.state !== "dialogue_unavailable" || !this.sessionId) return;
    const token = this.generation;
    this.setState("processing", "Retrying the Ollama caller response…");
    this.submissionInFlight = true;
    try {
      const data = await retryDialogue(this.sessionId);
      if (!this._isCurrent(token)) return;
      if (data.turn_id) {
        this.turnCount += 1;
        this.callbacks.onTurn?.(data);
      } else {
        this.callbacks.onRetry?.(data);
      }
      await this.playCaller(data, token, !this.typedFallback);
    } catch (error) {
      if (this._isCurrent(token)) {
        this.setState("dialogue_unavailable", "Caller dialogue is unavailable. Press Retry caller response.");
        this._setSupport(error.message || "Ollama did not provide a caller response.");
        this.callbacks.onDialogueUnavailable?.(error);
      }
    } finally {
      this.submissionInFlight = false;
    }
  }

  async endCall() {
    if (!this.active || this.state === "terminal" || this.submissionInFlight) return;
    const token = this.generation;
    this._abortRecognition();
    this._clearTimer();
    if (this.elements.audio) stopAudio(this.elements.audio);
    this.setState("processing", "Ending the fictional call safely…");
    this.submissionInFlight = true;
    try {
      const data = await requestEndCall(this.sessionId);
      if (!this._isCurrent(token)) return;
      this._enterTerminal();
      this.callbacks.onEnded?.(data);
    } catch (error) {
      if (this._isCurrent(token)) {
        this.setState("error", "The call could not be ended yet. Try End call safely again.");
        this.callbacks.onError?.(error);
      }
    } finally {
      this.submissionInFlight = false;
    }
  }
}
