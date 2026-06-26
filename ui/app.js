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

async function applySavedTheme() {
  try {
    const cfg = await window.afk.call('get_settings', {});
    applyTheme(cfg.theme);
  } catch (e) { /* default dark */ }
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

// ---------- Clarify (Phase 4) ----------
async function refreshClarifyStatus() {
  try {
    const s = await window.afk.call('clarify_status', {});
    const label = (st) => (st === 'loaded' ? 'ready' : st);
    $('#clarifyModels').textContent = `short: ${label(s.short)} · long: ${label(s.long)}`;
  } catch (e) { /* ignore */ }
}

async function clarifyText() {
  const btn = $('#clarifyBtn');
  const input = $('#clarifyInput').value.trim();
  if (!input) return;
  btn.disabled = true;
  btn.textContent = 'Clarifying…';
  $('#clarifyMeta').textContent = '';
  try {
    const res = await window.afk.call('clarify', { text: input });
    $('#clarifyOutput').textContent = res.text || '(no output)';
    const model = res.model && res.model !== 'none' ? res.model : 'no model installed';
    $('#clarifyMeta').textContent = `${res.words} words → ${model}` +
      (res.latency_ms ? ` · ${res.latency_ms} ms` : '');
  } catch (e) {
    $('#clarifyOutput').textContent = '⚠ ' + (e.message || 'Clarify failed');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Clarify';
  }
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

// ---------- Statistics (Phase 5) ----------
function fmtDuration(sec) {
  sec = Math.round(sec || 0);
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60), s = sec % 60;
  if (m < 60) return s ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function statCard(value, label, accent) {
  return `<div class="stat-card"><div class="stat-value${accent ? ' accent' : ''}">${value}</div>` +
    `<div class="stat-label">${label}</div></div>`;
}

async function refreshStatistics() {
  const grid = $('#statsGrid');
  try {
    const s = await window.afk.call('get_statistics', {});
    const todaySaved = (s.words.today / (s.typing_wpm_assumed || 40));
    grid.innerHTML =
      `<div class="stats-section-title">Words spoken</div>
       <div class="stats-grid">
         ${statCard(s.words.today.toLocaleString(), 'Today', true)}
         ${statCard(s.words.week.toLocaleString(), 'This week')}
         ${statCard(s.words.month.toLocaleString(), 'This month')}
         ${statCard(s.words.lifetime.toLocaleString(), 'All time')}
       </div>
       <div class="stats-section-title">Productivity</div>
       <div class="stats-grid">
         ${statCard(s.wpm_avg, 'Avg words/min', true)}
         ${statCard(fmtDuration(todaySaved * 60), 'Typing time saved (today)')}
         ${statCard(fmtDuration(s.typing_minutes_saved * 60), 'Typing time saved (all time)', true)}
         ${statCard(s.streak_current + ' 🔥', 'Current streak (days)')}
         ${statCard(s.streak_longest, 'Longest streak (days)')}
       </div>
       <div class="stats-section-title">Recordings & latency</div>
       <div class="stats-grid">
         ${statCard(s.recordings.toLocaleString(), 'Total recordings')}
         ${statCard(fmtDuration(s.longest_recording_sec), 'Longest recording')}
         ${statCard(fmtDuration(s.avg_recording_sec), 'Avg recording')}
         ${statCard(fmtDuration(s.total_transcription_sec), 'Total transcription time')}
         ${statCard(s.avg_transcription_latency_ms + ' ms', 'Avg transcription latency')}
         ${statCard(s.clarifications.toLocaleString(), 'Clarify requests')}
         ${statCard((s.avg_clarify_latency_ms || 0) + ' ms', 'Avg clarify latency')}
       </div>`;
  } catch (e) {
    grid.innerHTML = '<div class="empty-hint">Statistics unavailable (backend starting…)</div>';
  }
}

// ---------- Settings (Phase 5) ----------
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme === 'light' ? 'light' : 'dark');
}

function settingRow(name, desc, controlHtml) {
  return `<div class="setting-row"><div class="setting-text"><span class="setting-name">${name}</span>` +
    `<span class="setting-desc">${desc}</span></div><div class="setting-control">${controlHtml}</div></div>`;
}
function toggleHtml(id, checked) {
  return `<label class="switch"><input type="checkbox" id="${id}" ${checked ? 'checked' : ''}><span class="slider"></span></label>`;
}

let _settingsCache = null;
async function refreshSettings() {
  const list = $('#settingsList');
  try {
    const cfg = await window.afk.call('get_settings', {});
    _settingsCache = cfg;
    const mics = (await window.afk.call('list_microphones', {})).devices || [];
    const micOpts = ['<option value="">System default</option>']
      .concat(mics.map((d) => `<option value="${d.name}" ${cfg.microphone === d.name ? 'selected' : ''}>${d.name}</option>`))
      .join('');
    const hk = cfg.hotkeys || {};
    list.innerHTML =
      settingRow('Microphone', 'Input device for dictation', `<select id="set-microphone">${micOpts}</select>`) +
      settingRow('Theme', 'Appearance', `<select id="set-theme"><option value="dark" ${cfg.theme !== 'light' ? 'selected' : ''}>Dark</option><option value="light" ${cfg.theme === 'light' ? 'selected' : ''}>Light</option></select>`) +
      settingRow('Start on login', 'Launch AFK when Windows starts', toggleHtml('set-startup_on_login', cfg.startup_on_login)) +
      settingRow('Launch minimized', 'Start hidden in the system tray', toggleHtml('set-launch_minimized', cfg.launch_minimized)) +
      settingRow('Auto-paste', 'Paste transcription into the active app', toggleHtml('set-auto_paste', cfg.auto_paste)) +
      settingRow('Auto-clarify', 'Polish dictation with Clarify before pasting', toggleHtml('set-auto_clarify', cfg.auto_clarify)) +
      settingRow('Word-count threshold', 'Words above which the long (higher-quality) model is used', `<input type="number" id="set-word_count_threshold" min="1" max="500" value="${cfg.word_count_threshold}">`) +
      settingRow('Push-to-talk hotkey', 'Hold to record', `<input type="text" class="hotkey-input" id="hk-push_to_talk" value="${hk.push_to_talk || ''}">`) +
      settingRow('Toggle hotkey', 'Press to start/stop recording', `<input type="text" class="hotkey-input" id="hk-toggle" value="${hk.toggle || ''}">`) +
      settingRow('Clarify hotkey', 'Polish selected text or clipboard', `<input type="text" class="hotkey-input" id="hk-clarify" value="${hk.clarify || ''}">`) +
      settingRow('Logging', 'Write diagnostic logs to disk', toggleHtml('set-logging', cfg.logging)) +
      settingRow('Developer mode', 'Extra diagnostics and DevTools', toggleHtml('set-developer_mode', cfg.developer_mode)) +
      `<div class="settings-actions"><button class="btn" id="resetStatsBtn">Reset statistics</button></div>`;

    wireSettingControls();
  } catch (e) {
    list.innerHTML = '<div class="empty-hint">Settings unavailable (backend starting…)</div>';
  }
}

function wireSettingControls() {
  const patchToggle = (id, key) => {
    const el = $('#' + id);
    if (el) el.addEventListener('change', () => saveSetting(key, el.checked));
  };
  patchToggle('set-startup_on_login', 'startup_on_login');
  patchToggle('set-launch_minimized', 'launch_minimized');
  patchToggle('set-auto_paste', 'auto_paste');
  patchToggle('set-auto_clarify', 'auto_clarify');
  patchToggle('set-logging', 'logging');
  patchToggle('set-developer_mode', 'developer_mode');

  $('#set-microphone').addEventListener('change', (e) => saveSetting('microphone', e.target.value || null));
  $('#set-theme').addEventListener('change', (e) => { applyTheme(e.target.value); saveSetting('theme', e.target.value); });
  const thr = $('#set-word_count_threshold');
  thr.addEventListener('change', () => saveSetting('word_count_threshold', parseInt(thr.value, 10) || 60));

  ['push_to_talk', 'toggle', 'clarify'].forEach((k) => {
    const el = $('#hk-' + k);
    el.addEventListener('change', () => saveHotkeys());
  });

  $('#resetStatsBtn').addEventListener('click', async () => {
    await window.afk.call('reset_statistics', {});
    refreshStatistics();
  });
}

async function saveSetting(key, value) {
  try { await window.afk.call('update_settings', { patch: { [key]: value } }); refreshHotkeys(); } catch (e) {}
}
async function saveHotkeys() {
  const hotkeys = {
    push_to_talk: $('#hk-push_to_talk').value.trim(),
    toggle: $('#hk-toggle').value.trim(),
    clarify: $('#hk-clarify').value.trim(),
  };
  try { await window.afk.call('set_hotkeys', { hotkeys }); refreshHotkeys(); } catch (e) {}
}

// ---------- Backend events ----------
function initEvents() {
  window.afk.onBackendStatus(({ ready }) => {
    setBackendStatus(ready);
    if (ready) {
      refreshBackendInfo();
      refreshHotkeys();
      refreshMicrophones();
      refreshAsrStatus();
      refreshClarifyStatus();
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
      case 'clarify_done':
        if (data && data.text) {
          $('#clarifyOutput').textContent = data.text;
          $('#clarifyMeta').textContent = `${data.model || ''}` +
            (data.latency_ms ? ` · ${data.latency_ms} ms` : '');
        }
        break;
      case 'statistics_updated':
        if ($('#page-statistics').classList.contains('active')) refreshStatistics();
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
  $('#clarifyBtn').addEventListener('click', clarifyText);
  await initAbout();
  await refreshBackendInfo();
  await refreshHotkeys();
  await refreshMicrophones();
  await refreshAsrStatus();
  await refreshClarifyStatus();
  await applySavedTheme();
  // poll once more shortly after boot in case backend started late
  setTimeout(() => { refreshBackendInfo(); refreshAsrStatus(); }, 1500);
  // keep ASR status fresh while it loads in the background
  const asrPoll = setInterval(refreshAsrStatus, 2500);
  setTimeout(() => clearInterval(asrPoll), 60000);
});
