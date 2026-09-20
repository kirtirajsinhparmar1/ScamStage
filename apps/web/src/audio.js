import { API_BASE } from "./api.js";

export function stopAudio(player) {
  player.pause();
  player.onended = null;
  player.onerror = null;
  player.removeAttribute("src");
  player.load();
  player.hidden = true;
}

export async function playResponse(player, status, audioUrl, { onEnded, onError, onBlocked } = {}) {
  stopAudio(player);
  if (!audioUrl) {
    status.textContent = "Text-only mode: voice is unavailable. Continue using the transcript.";
    return;
  }
  player.src = new URL(audioUrl, API_BASE).href;
  player.hidden = false;
  status.textContent = "Synthetic training audio · ElevenLabs";
  player.onended = () => onEnded?.();
  player.onerror = () => {
    status.textContent = "Audio could not be loaded. Continue with the fictional transcript.";
    onError?.();
  };
  try {
    await player.play();
    return true;
  } catch {
    status.textContent = "Press play to hear the synthetic response. Your browser may block automatic playback.";
    onBlocked?.();
    return false;
  }
}
