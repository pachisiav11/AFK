'use strict';

/**
 * AFK renderer. Talks to the backend only via the whitelisted `window.afk`
 * bridge (see electron/preload.js). No Node access here.
 */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

// ---------- Navigation ----------
function initNav() {
  $$('.nav-item').forEach((btn) => {
    btn.addEventListener('click', () => {
      const page = btn.dataset.page;
      $$('.nav-item').forEach((b) => b.classList.toggle('active', b === btn));
      $$('.page').forEach((p) => p.classList.toggle('active', p.id === `page-${page}`));
      if (page === 'statistics') refreshStatistics();
      if (page === 'settings') refreshSettings();
    });
  });
}

// ---------- Backend status ----------
function setBackendStatus(ready) {
  const dot = $('#backendDot');
  const label = $('#backendLabel');
  dot.className = 'dot ' + (ready ? 'dot-ok' : 'dot-bad');
  label.textContent = ready ? 'Backend ready' : 'Backend offline';
  if (!ready) {
    dot.className = 'dot dot-pending';
    label.textContent = 'Starting backend…';
  }
}

// ---------- About page ----------
async function initAbout() {
  try {
    const info = await window.afk.app.getInfo();
    $('#aboutVersion').textContent = info.version;
    $('#aboutElectron').textContent = info.electron;
    $('#aboutNode').textContent = info.node;
  } catch (e) { /* ignore */ }
}

async function refreshBackendInfo() {
  try {
    const ready = await window.afk.backendReady();
    setBackendStatus(ready);
    if (ready) {
      const info = await window.afk.call('get_info', {});
      $('#aboutBackend').textContent = `${info.backend} (py ${info.python})`;
      $('#aboutModels').textContent = info.models_status || 'not loaded';
      $('#activeModel').textContent = info.default_model || '—';
    }
  } catch (e) { /* backend may still be booting */ }
}

// ---------- Microphones + ASR (Phase 2) ----------
async function refreshMicrophones() {
  try {
    const { devices } = await window.afk.call('list_microphones', {});
    const sel = $('#micSelect');
    const current = sel.value;
    sel.innerHTML = '<option value="">System default</option>';
    (devices || []).forEach((d) => {
      const opt = document.createElement('option');
      opt.value = d.name;
      opt.textContent = d.default ? `${d.name} (default)` : d.name;
      sel.appendChild(opt);
    });
    const saved = (await window.afk.call('get_settings', {})).microphone;
    sel.value = saved || current || '';
  } catch (e) { /* backend booting */ }
}

async function refreshAsrStatus() {
  try {
    const { status } = await window.afk.call('asr_status', {});
    const map = { loaded: 'Model: ready', loading: 'Model: loading…', 'not loaded': 'Model: idle' };
    $('#asrStatus').textContent = map[status] || `Model: ${status}`;
  } catch (e) { /* ignore */ }
}

let isRecording = false;
async function toggleRecord() {
  const btn = $('#recordBtn');
  try {
    if (!isRecording) {
      const device = $('#micSelect').value || null;
      await window.afk.call('start_recording', { device });
      isRecording = true;
      btn.textContent = 'Stop & transcribe';
      btn.classList.add('recording');
    } else {
      btn.textContent = 'Transcribing…';
      btn.disabled = true;
      const res = await window.afk.call('stop_recording', {});
      isRecording = false;
      btn.disabled = false;
      btn.textContent = 'Start recording';
      btn.classList.remove('recording');
      if (res && res.text) showTranscription(res.text);
    }
  } catch (e) {
    isRecording = false;
    btn.disabled = false;
    btn.textContent = 'Start recording';
    btn.classList.remove('recording');
    showTranscription('⚠ ' + (e.message || 'Recording failed'));
  }
}

async function onMicChange() {
  const value = $('#micSelect').value || null;
  try { await window.afk.call('update_settings', { patch: { microphone: value } }); } catch (e) {}
}

// ---------- Hotkeys display (filled in later phases) ----------
async function refreshHotkeys() {
  try {
    const cfg = await window.afk.call('get_settings', {});
    const hk = (cfg && cfg.hotkeys) || {};
    $('#pttHotkey').textContent = hk.push_to_talk || 'Ctrl+Space (hold)';
    $('#toggleHotkey').textContent = hk.toggle || 'Ctrl+Shift+Space';
    $('#clarifyHotkey').textContent = hk.clarify || 'Ctrl+Shift+C';
  } catch (e) {
    // defaults until backend is ready
    $('#pttHotkey').textContent = 'Ctrl+Space (hold)';
    $('#toggleHotkey').textContent = 'Ctrl+Shift+Space';
    $('#clarifyHotkey').textContent = 'Ctrl+Shift+C';
  }
}

// ---------- Placeholders for later phases ----------
async function refreshStatistics() { /* Phase 5 */ }
async function refreshSettings() { /* Phase 5 */ }

// ---------- Backend events ----------
function initEvents() {
  window.afk.onBackendStatus(({ ready }) => {
    setBackendStatus(ready);
    if (ready) {
      refreshBackendInfo();
      refreshHotkeys();
      refreshMicrophones();
      refreshAsrStatus();
    }
  });

  window.afk.onBackendEvent(({ event, data }) => {
    switch (event) {
      case 'recording_started':
        setRecording(true);
        break;
      case 'recording_stopped':
        setRecording(false);
        break;
      case 'transcription':
        showTranscription(data && data.text);
        break;
      default:
        break;
    }
  });
}

let recTimer = null;
let recStart = 0;
function setRecording(on) {
  const orb = $('#recordOrb');
  const status = $('#recordStatus');
  orb.classList.toggle('recording', on);
  status.textContent = on ? 'Recording…' : 'Idle';
  if (on) {
    recStart = Date.now();
    recTimer = setInterval(() => {
      const s = Math.floor((Date.now() - recStart) / 1000);
      const mm = String(Math.floor(s / 60)).padStart(2, '0');
      const ss = String(s % 60).padStart(2, '0');
      $('#recordTimer').textContent = `${mm}:${ss}`;
    }, 250);
  } else {
    clearInterval(recTimer);
  }
}

function showTranscription(text) {
  const el = $('#transcription');
  if (text) el.textContent = text;
}

// ---------- Boot ----------
window.addEventListener('DOMContentLoaded', async () => {
  initNav();
  initEvents();
  $('#recordBtn').addEventListener('click', toggleRecord);
  $('#micSelect').addEventListener('change', onMicChange);
  await initAbout();
  await refreshBackendInfo();
  await refreshHotkeys();
  await refreshMicrophones();
  await refreshAsrStatus();
  // poll once more shortly after boot in case backend started late
  setTimeout(() => { refreshBackendInfo(); refreshAsrStatus(); }, 1500);
  // keep ASR status fresh while it loads in the background
  const asrPoll = setInterval(refreshAsrStatus, 2500);
  setTimeout(() => clearInterval(asrPoll), 60000);
});
