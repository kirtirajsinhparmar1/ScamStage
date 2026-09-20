import { API_BASE } from "./api.js";

export function stopAudio(player) {
  player.pause();
  player.removeAttribute("src");
  player.load();
  player.hidden = true;
}

export async function playResponse(player, status, audioUrl) {
  stopAudio(player);
  if (!audioUrl) {
    status.textContent = "Text-only mode: voice is unavailable. Continue using the transcript.";
    return;
  }
  player.src = new URL(audioUrl, API_BASE).href;
  player.hidden = false;
  status.textContent = "Synthetic training audio · ElevenLabs";
  try {
    await player.play();
  } catch {
    status.textContent = "Press play to hear the synthetic response. Your browser may block automatic playback.";
  }
}
