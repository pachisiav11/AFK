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

// ---------- Hotkeys display (filled in later phases) ----------
async function refreshHotkeys() {
  try {
    const cfg = await window.afk.call('get_settings', {});
    const hk = (cfg && cfg.hotkeys) || {};
    $('#pttHotkey').textContent = hk.push_to_talk || 'Ctrl+Space (hold)';
    $('#toggleHotkey').textContent = hk.toggle || 'Ctrl+Shift+Space';
    $('#clarifyHotkey').textContent = hk.clarify || 'Ctrl+Shift+C';
    if (cfg && cfg.microphone) $('#activeMic').textContent = cfg.microphone;
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
  await initAbout();
  await refreshBackendInfo();
  await refreshHotkeys();
  // poll once more shortly after boot in case backend started late
  setTimeout(refreshBackendInfo, 1500);
});
