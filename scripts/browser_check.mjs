// Browser integration check using an already running local Chrome debugging port.
// Requires Node 22+ (native WebSocket); no npm dependencies.
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';

const args = process.argv.slice(2);
const option = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
const base = option('--base-url', 'http://127.0.0.1:8001');
const cdp = option('--cdp-url', 'http://127.0.0.1:9222');
const live = args.includes('--require-live');
const checkTimeoutLabel = args.includes('--check-timeout-label');
assert(!live || !checkTimeoutLabel, 'Timeout-label fixture is only for the fallback server');
const singleSession = args.includes('--single-session');
const scenarioId = option('--scenario-id', live ? 'fictional_job_recruiter_v1' : null);
assert(!live || singleSession, '--require-live requires --single-session; test the branch matrix on the fallback server');
// Covers the adapter's maximum two-attempt budget plus voice synthesis.
const readyTimeout = live ? 260000 : 55000;
const pages = await (await fetch(`${cdp}/json`)).json();
const page = pages.find(item => item.type === 'page');
assert(page, 'Open a Chrome debugging tab first');
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true });
  socket.addEventListener('error', reject, { once: true });
});
let sequence = 0;
const pending = new Map();
const errors = [];
socket.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
  const handler = pending.get(message.id);
  if (handler) {
    pending.delete(message.id);
    clearTimeout(handler.timer);
    if (message.error) handler.reject(new Error(message.error.message));
    else handler.resolve(message.result);
  }
});
function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Timeout: ${method}`)); }, readyTimeout + 5000);
    pending.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expression) {
  const result = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
  assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function until(expression) {
  await evaluate(`new Promise((resolve,reject) => {
    const deadline = Date.now() + ${readyTimeout};
    const poll = () => { if (${expression}) resolve(true);
      else if (Date.now() > deadline) reject(new Error('UI did not become ready'));
      else setTimeout(poll, 100); }; poll(); })`);
}
const text = id => evaluate(`document.getElementById(${JSON.stringify(id)}).textContent`);
async function audioCheck() {
  if (!live) return;
  const result = await evaluate(`(async () => {
    const audio = document.getElementById('audio');
    if (!audio.src || audio.hidden) throw new Error('Missing live audio');
    const initialTime = audio.currentTime;
    await audio.play();
    const deadline = Date.now() + 5000;
    while (audio.currentTime <= initialTime && !audio.error && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    const result = {time:audio.currentTime, advanced:audio.currentTime > initialTime, ready:audio.readyState, error:audio.error?.code};
    audio.pause(); return result;
  })()`);
  assert(result.advanced && result.time > 0 && result.ready >= 2 && !result.error, JSON.stringify(result));
}
try {
  await call('Runtime.enable');
  await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride', { width:1280, height:1100, deviceScaleFactor:1, mobile:false });
  await call('Page.navigate', { url:base });
  await until("document.querySelectorAll('#scenario option').length === 3 && !document.getElementById('start').disabled");
  if (checkTimeoutLabel) {
    // Only inject the sanitized reason on an already-declared fallback response.
    // Branch, evidence, risk, and debrief remain the real deterministic API output.
    await evaluate(`(() => {
      const originalFetch = window.fetch.bind(window);
      window.fetch = async (...request) => {
        const response = await originalFetch(...request);
        if (!String(request[0]).endsWith('/turns') || !response.ok) return response;
        const data = await response.clone().json();
        if (data.classifier_fallback !== true) throw new Error('Timeout fixture requires fallback server');
        data.classifier_fallback_reason = 'timeout';
        return new Response(JSON.stringify(data), {status:response.status, headers:{'Content-Type':'application/json'}});
      };
    })()`);
  }
  const scenarios = await evaluate("Array.from(document.querySelectorAll('#scenario option'), o => ({id:o.value,name:o.textContent}))");
  assert.equal(scenarios.length, 3);
  const selected = scenarioId ? scenarios.filter(scenario => scenario.id === scenarioId) : scenarios;
  assert(selected.length > 0, 'Requested scenario is not in the picker');
  for (const scenario of singleSession ? selected.slice(0, 1) : selected) {
    for (const risky of singleSession ? [false] : [false, true]) {
      await evaluate(`document.getElementById('another-scenario').click(); document.getElementById('scenario').value=${JSON.stringify(scenario.id)}; document.getElementById('scenario').dispatchEvent(new Event('change')); document.getElementById('start').click()`);
      await until("!document.getElementById('start').disabled && !document.getElementById('participant-text').disabled");
      assert((await text('selected-scenario')).includes(scenario.name));
      await audioCheck();
      for (const response of risky ? ['I will follow those instructions.', 'I will follow those instructions.'] : ['I am hanging up.']) {
        await evaluate(`document.getElementById('participant-text').value=${JSON.stringify(response)}; document.getElementById('turn-form').requestSubmit()`);
        await until("!document.getElementById('start').disabled");
        if (live) {
          assert((await text('providers')).includes('nemotron'));
          assert((await text('providers')).includes('elevenlabs'));
          assert(!(await text('providers')).toLowerCase().includes('fallback'));
        }
        if (checkTimeoutLabel) {
          assert((await text('providers')).includes('Classifier: deterministic fallback (timeout)'));
        }
        await audioCheck();
      }
      const outcome = live ? await text('stage') : risky ? 'risky outcome' : 'safe exit';
      if (!live) assert.equal(await text('stage'), outcome);
      const terminal = ['safe exit', 'risky outcome'].includes(outcome);
      if (terminal) {
        assert((await text('debrief-heading')).includes(scenario.name));
        assert((await text('debrief-outcome')).includes(outcome));
      }
      const timeline = await text('timeline');
      assert(timeline.includes(outcome) && timeline.includes('confidence') && timeline.includes('evidence:'));
      assert.equal(await evaluate("document.getElementById('send').disabled"), terminal);
      assert.equal(await evaluate("document.getElementById('debrief').hidden"), !terminal);
      console.log(`PASS browser: ${scenario.id} ${outcome}${live ? ' + live classification/audio playback' : ''}`);
    }
  }
  await evaluate('window.scrollTo(0,0)');
  const shot = await call('Page.captureScreenshot', { format:'png', captureBeyondViewport:true });
  await writeFile('/private/tmp/scamstage-milestone2-desktop.png', Buffer.from(shot.data, 'base64'));
  await call('Emulation.setDeviceMetricsOverride', { width:390, height:844, deviceScaleFactor:1, mobile:true });
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true, 'Mobile horizontal overflow');
  const mobile = await call('Page.captureScreenshot', { format:'png', captureBeyondViewport:true });
  await writeFile('/private/tmp/scamstage-milestone2-mobile.png', Buffer.from(mobile.data, 'base64'));
  assert.deepEqual(errors, []);
  console.log('PASS desktop/mobile layout and zero uncaught browser errors');
} finally {
  socket.close();
}
