'use strict';

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

let isRecording = false;
let recTimer = null;
let recStart = 0;
let _settingsCache = null;
let activeTrainingKind = null;

const DEFAULT_HOTKEYS = {
  push_to_talk: 'Ctrl+Shift+Space',
  toggle: 'Ctrl+Alt+Space',
  clarify: 'Ctrl+Alt+K',
  learn_correction: 'Ctrl+Alt+L'
};

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ---------- Navigation ----------
function initNav() {
  $$('.nav-item').forEach((btn) => {
    btn.addEventListener('click', () => {
      const page = btn.dataset.page;
      $$('.nav-item').forEach((b) => b.classList.toggle('active', b === btn));
      $$('.page').forEach((p) => p.classList.toggle('active', p.id === `page-${page}`));
      if (page === 'home') refreshHomeStats();
      if (page === 'statistics') refreshStatistics();
      if (page === 'train') refreshTrain();
      if (page === 'settings') refreshSettings();
    });
  });
}

// ---------- Backend status ----------
function setBackendStatus(ready) {
  const dot = $('#backendDot');
  const label = $('#backendLabel');
  dot.className = ready ? 'dot dot-ok' : 'dot dot-pending';
  label.textContent = ready ? 'Backend ready' : 'Starting backend...';
}

async function initAbout() {
  try {
    const info = await window.afk.app.getInfo();
    $('#aboutVersion').textContent = info.version;
    $('#aboutElectron').textContent = info.electron;
    $('#aboutNode').textContent = info.node;
  } catch (e) {
    // Backend shell can still be starting.
  }
}

async function applySavedTheme() {
  try {
    const cfg = await window.afk.call('get_settings', {});
    _settingsCache = cfg;
    applyTheme(cfg.theme);
  } catch (e) {
    applyTheme('dark');
  }
}

async function refreshBackendInfo() {
  try {
    const ready = await window.afk.backendReady();
    setBackendStatus(ready);
    if (!ready) return;
    const info = await window.afk.call('get_info', {});
    $('#aboutBackend').textContent = `${info.backend} (py ${info.python})`;
    $('#aboutModels').textContent = info.models_status || 'not loaded';
    $('#activeModel').textContent = 'Parakeet + Gemma';
  } catch (e) {
    setBackendStatus(false);
  }
}

// ---------- Microphones + ASR ----------
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
    const cfg = await window.afk.call('get_settings', {});
    _settingsCache = cfg;
    sel.value = cfg.microphone || current || '';
  } catch (e) {
    // Backend may still be booting.
  }
}

async function refreshAsrStatus() {
  try {
    const { status, engine } = await window.afk.call('asr_status', {});
    const map = {
      loaded: 'ready',
      loading: 'loading',
      'not loaded': 'idle'
    };
    $('#asrStatus').textContent = `Speech: ${engine || 'auto'} / ${map[status] || status}`;
  } catch (e) {
    $('#asrStatus').textContent = 'Speech: starting';
  }
}

async function loadAsrModel() {
  const btn = $('#loadAsrBtn');
  btn.disabled = true;
  btn.textContent = 'Loading...';
  $('#asrStatus').textContent = 'Speech: loading';
  try {
    const res = await window.afk.call('load_asr', {});
    $('#asrStatus').textContent = `Speech: ${res.status || 'ready'}`;
  } catch (e) {
    $('#asrStatus').textContent = 'Speech: error';
    showTranscription(`ASR load failed: ${e.message || e}`);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Load speech model';
  }
}

async function toggleRecord() {
  const btn = $('#recordBtn');
  try {
    if (!isRecording) {
      const device = $('#micSelect').value || null;
      await window.afk.call('start_recording', { device });
      isRecording = true;
      btn.textContent = 'Stop and transcribe';
      btn.classList.add('recording');
      return;
    }

    btn.textContent = 'Transcribing...';
    btn.disabled = true;
    const res = await window.afk.call('finish_recording', {});
    isRecording = false;
    btn.classList.remove('recording');
    if (res && res.text) {
      const action = res.action === 'pasted' ? 'Pasted.' : 'Copied to clipboard.';
      showTranscription(res.text, action);
      $('#recordStatus').textContent = res.action === 'pasted' ? 'Pasted' : 'Copied';
    } else if (res && res.message) {
      showTranscription('', res.message);
    }
  } catch (e) {
    isRecording = false;
    btn.classList.remove('recording');
    showTranscription(`Recording failed: ${e.message || e}`);
  } finally {
    if (!isRecording) {
      btn.disabled = false;
      btn.textContent = 'Start recording';
    }
    refreshAsrStatus();
  }
}

async function onMicChange() {
  const value = $('#micSelect').value || null;
  try {
    await window.afk.call('update_settings', { patch: { microphone: value } });
  } catch (e) {
    // Ignore transient backend startup failures.
  }
}

// ---------- Clarify ----------
async function refreshClarifyStatus() {
  try {
    const s = await window.afk.call('clarify_status', {});
    const clean = (value) => value === 'loaded' ? 'ready' : value;
    $('#clarifyModels').textContent = `Clarify: ${clean(s.short)} / ${clean(s.long)}`;
  } catch (e) {
    $('#clarifyModels').textContent = 'Clarify: starting';
  }
}

async function clarifyText() {
  const btn = $('#clarifyBtn');
  const input = $('#clarifyInput').value.trim();
  if (!input) return;
  btn.disabled = true;
  btn.textContent = 'Clarifying...';
  $('#clarifyMeta').textContent = '';
  try {
    const res = await window.afk.call('clarify', { text: input });
    $('#clarifyOutput').textContent = res.text || '(no output)';
    const model = res.model && res.model !== 'none' ? res.model : 'no model';
    $('#clarifyMeta').textContent = `${res.words} words / ${model}` +
      (res.latency_ms ? ` / ${res.latency_ms} ms` : '');
  } catch (e) {
    $('#clarifyOutput').textContent = `Clarify failed: ${e.message || e}`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Clarify';
    refreshClarifyStatus();
  }
}

// ---------- Hotkeys ----------
async function refreshHotkeys() {
  try {
    const cfg = await window.afk.call('get_settings', {});
    _settingsCache = cfg;
    const hk = cfg.hotkeys || {};
    $('#pttHotkey').textContent = hk.push_to_talk || DEFAULT_HOTKEYS.push_to_talk;
    $('#toggleHotkey').textContent = hk.toggle || DEFAULT_HOTKEYS.toggle;
    $('#clarifyHotkey').textContent = hk.clarify || DEFAULT_HOTKEYS.clarify;
    $('#learnHotkey').textContent = hk.learn_correction || DEFAULT_HOTKEYS.learn_correction;
  } catch (e) {
    $('#pttHotkey').textContent = DEFAULT_HOTKEYS.push_to_talk;
    $('#toggleHotkey').textContent = DEFAULT_HOTKEYS.toggle;
    $('#clarifyHotkey').textContent = DEFAULT_HOTKEYS.clarify;
    $('#learnHotkey').textContent = DEFAULT_HOTKEYS.learn_correction;
  }
}

function isEditableTarget(target) {
  if (!target) return false;
  if (target.isContentEditable) return true;
  const tag = String(target.tagName || '').toLowerCase();
  return tag === 'input' || tag === 'textarea' || tag === 'select';
}

function comboFromEvent(event) {
  const key = event.key;
  const lower = String(key || '').toLowerCase();
  if (['control', 'shift', 'alt', 'meta'].includes(lower)) return '';

  const parts = [];
  if (event.ctrlKey) parts.push('Ctrl');
  if (event.shiftKey) parts.push('Shift');
  if (event.altKey) parts.push('Alt');
  if (event.metaKey) parts.push('Win');

  let main = '';
  if (event.code === 'Space' || lower === ' ') main = 'Space';
  else if (/^Key[A-Z]$/.test(event.code)) main = event.code.slice(3);
  else if (/^Digit[0-9]$/.test(event.code)) main = event.code.slice(5);
  else if (/^F[0-9]{1,2}$/.test(event.key)) main = event.key.toUpperCase();
  else if (lower === 'escape') main = 'Esc';
  else if (lower === 'arrowup') main = 'Up';
  else if (lower === 'arrowdown') main = 'Down';
  else if (lower === 'arrowleft') main = 'Left';
  else if (lower === 'arrowright') main = 'Right';
  else if (key && key.length === 1) main = key.toUpperCase();
  else if (key) main = key.charAt(0).toUpperCase() + key.slice(1);

  if (!main) return '';
  parts.push(main);
  return parts.join('+');
}

function normalizeCombo(combo) {
  if (!combo) return '';
  const mods = [];
  let main = '';
  String(combo).split('+').forEach((part) => {
    const p = part.trim().toLowerCase();
    if (!p) return;
    if (['ctrl', 'control', 'ctl'].includes(p)) mods.push('ctrl');
    else if (p === 'shift') mods.push('shift');
    else if (['alt', 'option', 'altgr'].includes(p)) mods.push('alt');
    else if (['win', 'cmd', 'super', 'meta', 'windows'].includes(p)) mods.push('win');
    else if (['space', 'spacebar'].includes(p)) main = 'space';
    else if (p === 'esc') main = 'escape';
    else main = p;
  });
  const order = ['ctrl', 'shift', 'alt', 'win'];
  return order.filter((m) => mods.includes(m)).concat(main ? [main] : []).join('+');
}

function eventMatchesCombo(event, combo) {
  return normalizeCombo(comboFromEvent(event)) === normalizeCombo(combo);
}

function configuredHotkeys() {
  const hk = (_settingsCache && _settingsCache.hotkeys) || {};
  return [
    hk.push_to_talk || DEFAULT_HOTKEYS.push_to_talk,
    hk.toggle || DEFAULT_HOTKEYS.toggle,
    hk.clarify || DEFAULT_HOTKEYS.clarify,
    hk.learn_correction || DEFAULT_HOTKEYS.learn_correction
  ];
}

function initEditableHotkeyHandling() {
  document.addEventListener('keydown', (event) => {
    const target = event.target;
    if (target && target.classList && target.classList.contains('hotkey-input')) {
      event.preventDefault();
      event.stopPropagation();
      if (event.key === 'Backspace' || event.key === 'Delete') {
        target.value = '';
        saveHotkeys();
        return;
      }
      const combo = comboFromEvent(event);
      if (combo) {
        target.value = combo;
        saveHotkeys();
      }
      return;
    }

    if (!isEditableTarget(target)) return;
    if (configuredHotkeys().some((combo) => eventMatchesCombo(event, combo))) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);

  document.addEventListener('keyup', (event) => {
    if (!isEditableTarget(event.target)) return;
    if (configuredHotkeys().some((combo) => eventMatchesCombo(event, combo))) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
}

// ---------- Statistics ----------
function fmtDuration(sec) {
  sec = Math.round(sec || 0);
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m < 60) return s ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function statCard(value, label, accent) {
  return `<div class="stat-card"><div class="stat-value${accent ? ' accent' : ''}">${escapeHtml(value)}</div>` +
    `<div class="stat-label">${escapeHtml(label)}</div></div>`;
}

function homeStatCard(value, label, accent) {
  return `<div class="home-stat"><strong${accent ? ' class="accent"' : ''}>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`;
}

function barMeter(label, value, max, accent) {
  const pct = Math.max(3, Math.min(100, max ? (Number(value || 0) / max) * 100 : 0));
  return `<div class="bar-row"><span>${escapeHtml(label)}</span><div class="bar-track"><i class="${accent ? 'accent' : ''}" style="width:${pct}%"></i></div><b>${escapeHtml(value)}</b></div>`;
}

function sparkBars(values) {
  const max = Math.max(1, ...values.map((v) => Number(v || 0)));
  return `<div class="spark-bars">${values.map((v, i) => {
    const h = Math.max(12, Math.round((Number(v || 0) / max) * 76));
    return `<span style="height:${h}px" title="Bucket ${i + 1}: ${escapeHtml(v)}"></span>`;
  }).join('')}</div>`;
}

async function refreshHomeStats() {
  const box = $('#homeStats');
  if (!box) return;
  try {
    const [s, adaptation] = await Promise.all([
      window.afk.call('get_statistics', {}),
      window.afk.call('get_adaptation', {})
    ]);
    const saved = fmtDuration((s.words.today / (s.typing_wpm_assumed || 40)) * 60);
    box.innerHTML =
      homeStatCard(s.words.today.toLocaleString(), 'Words today', true) +
      homeStatCard(s.words.week.toLocaleString(), 'Words this week') +
      homeStatCard(saved, 'Typing saved today', true) +
      homeStatCard((adaptation.training_count || 0).toLocaleString(), 'Training samples');
  } catch (e) {
    box.innerHTML = '<div class="empty-hint">Statistics unavailable while the backend starts.</div>';
  }
}

async function refreshStatistics() {
  const grid = $('#statsGrid');
  try {
    const s = await window.afk.call('get_statistics', {});
    const todaySaved = (s.words.today / (s.typing_wpm_assumed || 40));
    const wordMax = Math.max(1, s.words.today, s.words.week, s.words.month);
    const latencyBuckets = [
      Math.max(1, Math.round((s.avg_transcription_latency_ms || 0) / 100)),
      s.clarifications || 0,
      Math.max(1, Math.round((s.avg_clarify_latency_ms || 0) / 100)),
      s.recordings || 0,
      Math.max(1, s.streak_current || 0)
    ];
    grid.innerHTML =
      `<section class="stats-section">
        <div class="stats-section-title">Words spoken</div>
        <div class="stats-grid stats-grid-featured">
          ${statCard(s.words.today.toLocaleString(), 'Today', true)}
          <div class="stat-card chart-card">
            ${barMeter('Today', s.words.today, wordMax, true)}
            ${barMeter('Week', s.words.week, wordMax, false)}
            ${barMeter('Month', s.words.month, wordMax, false)}
          </div>
          ${statCard(s.words.lifetime.toLocaleString(), 'All time')}
        </div>
      </section>
      <section class="stats-section">
        <div class="stats-section-title">Productivity</div>
        <div class="stats-grid">
          ${statCard(s.wpm_avg, 'Average words/min', true)}
          ${statCard(fmtDuration(todaySaved * 60), 'Typing time saved today')}
          ${statCard(fmtDuration(s.typing_minutes_saved * 60), 'Typing time saved total', true)}
          ${statCard(s.streak_current, 'Current streak days')}
          ${statCard(s.streak_longest, 'Longest streak days')}
        </div>
      </section>
      <section class="stats-section">
        <div class="stats-section-title">Recordings and latency</div>
        <div class="stats-grid">
          ${statCard(s.recordings.toLocaleString(), 'Total recordings')}
          ${statCard(fmtDuration(s.longest_recording_sec), 'Longest recording')}
          ${statCard(fmtDuration(s.avg_recording_sec), 'Average recording')}
          <div class="stat-card chart-card">
            <div class="chart-title">Activity pulse</div>
            ${sparkBars(latencyBuckets)}
          </div>
          ${statCard(fmtDuration(s.total_transcription_sec), 'Total transcription time')}
          ${statCard(`${s.avg_transcription_latency_ms} ms`, 'Average transcription latency')}
          ${statCard(s.clarifications.toLocaleString(), 'Clarify requests')}
          ${statCard(`${s.avg_clarify_latency_ms || 0} ms`, 'Average Clarify latency')}
        </div>
      </section>`;
  } catch (e) {
    grid.innerHTML = '<div class="empty-hint">Statistics unavailable while the backend starts.</div>';
  }
}

// ---------- Train ----------
function trainingItem(item) {
  const kind = item.kind === 'trigger' ? 'Trigger' : 'Word';
  const heard = item.heard ? `Parakeet heard: ${item.heard}` : 'No audio sample captured';
  return `<div class="training-item">
    <div><strong>${escapeHtml(kind)}</strong><span>${escapeHtml(item.spoken || '')}</span></div>
    <div><b>${escapeHtml(item.output || '')}</b><small>${escapeHtml(heard)}</small></div>
  </div>`;
}

async function refreshTrain() {
  try {
    const adaptation = await window.afk.call('get_adaptation', {});
    $('#trainSummary').textContent = `${adaptation.training_count || 0} samples`;
    const items = (adaptation.training || []).slice(-8).reverse();
    $('#trainingList').innerHTML = items.length
      ? items.map(trainingItem).join('')
      : '<div class="empty-hint">No training samples yet.</div>';
  } catch (e) {
    $('#trainSummary').textContent = 'starting';
    $('#trainingList').innerHTML = '<div class="empty-hint">Training unavailable while the backend starts.</div>';
  }
}

async function startTrainSample(kind) {
  const isTrigger = kind === 'trigger';
  const spoken = (isTrigger ? $('#trainTriggerInput') : $('#trainWordInput')).value.trim();
  const output = (isTrigger ? $('#trainOutputInput').value.trim() : spoken);
  const status = isTrigger ? $('#trainTriggerStatus') : $('#trainWordStatus');
  if (!spoken || !output) {
    status.textContent = isTrigger ? 'Add both the spoken trigger and output first.' : 'Type the word or phrase first.';
    return;
  }
  try {
    activeTrainingKind = kind;
    status.textContent = 'Recording... say it naturally once.';
    await window.afk.call('start_training_sample', {
      kind,
      spoken,
      output,
      device: $('#micSelect') ? ($('#micSelect').value || null) : null
    });
  } catch (e) {
    activeTrainingKind = null;
    status.textContent = `Training failed to start: ${e.message || e}`;
  }
}

async function finishTrainSample(kind) {
  const status = kind === 'trigger' ? $('#trainTriggerStatus') : $('#trainWordStatus');
  try {
    status.textContent = 'Transcribing sample and saving correction...';
    const res = await window.afk.call('finish_training_sample', {});
    activeTrainingKind = null;
    const heard = (res && res.training && res.training.heard) || (res && res.text) || '';
    status.textContent = heard ? `Saved. Parakeet heard "${heard}".` : 'Saved, but no speech was detected in that sample.';
    refreshTrain();
    refreshHomeStats();
  } catch (e) {
    activeTrainingKind = null;
    status.textContent = `Training failed: ${e.message || e}`;
  }
}

function initTrainControls() {
  $('#trainWordStartBtn').addEventListener('click', () => startTrainSample('word'));
  $('#trainWordFinishBtn').addEventListener('click', () => finishTrainSample('word'));
  $('#trainTriggerStartBtn').addEventListener('click', () => startTrainSample('trigger'));
  $('#trainTriggerFinishBtn').addEventListener('click', () => finishTrainSample('trigger'));
  $('#clearTrainingBtn').addEventListener('click', async () => {
    await window.afk.call('clear_adaptation', {});
    $('#trainWordStatus').textContent = 'Training memory cleared.';
    $('#trainTriggerStatus').textContent = 'Training memory cleared.';
    refreshTrain();
    refreshHomeStats();
  });
}

// ---------- Settings ----------
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme === 'light' ? 'light' : 'dark');
}

function settingRow(name, desc, controlHtml) {
  return `<div class="setting-row"><div class="setting-text"><span class="setting-name">${escapeHtml(name)}</span>` +
    `<span class="setting-desc">${escapeHtml(desc)}</span></div><div class="setting-control">${controlHtml}</div></div>`;
}

function toggleHtml(id, checked) {
  return `<label class="switch" aria-label="${escapeHtml(id)}"><input type="checkbox" id="${id}" ${checked ? 'checked' : ''}><span class="slider"></span></label>`;
}

async function refreshSettings() {
  const list = $('#settingsList');
  try {
    const cfg = await window.afk.call('get_settings', {});
    _settingsCache = cfg;
    const mics = (await window.afk.call('list_microphones', {})).devices || [];
    const micOpts = ['<option value="">System default</option>']
      .concat(mics.map((d) =>
        `<option value="${escapeHtml(d.name)}" ${cfg.microphone === d.name ? 'selected' : ''}>${escapeHtml(d.name)}</option>`
      ))
      .join('');
    const hk = cfg.hotkeys || {};

    list.innerHTML =
      settingRow('Microphone', 'Input device for dictation', `<select id="set-microphone">${micOpts}</select>`) +
      settingRow('Theme', 'Application appearance', `<select id="set-theme"><option value="dark" ${cfg.theme !== 'light' ? 'selected' : ''}>Dark</option><option value="light" ${cfg.theme === 'light' ? 'selected' : ''}>Light</option></select>`) +
      settingRow('Start on login', 'Launch AFK when Windows starts', toggleHtml('set-startup_on_login', cfg.startup_on_login)) +
      settingRow('Launch minimized', 'Open directly into the system tray', toggleHtml('set-launch_minimized', cfg.launch_minimized)) +
      settingRow('Auto-paste', 'Paste dictation into the active app', toggleHtml('set-auto_paste', cfg.auto_paste)) +
      settingRow('Auto-clarify', 'Run grammar cleanup before paste', toggleHtml('set-auto_clarify', cfg.auto_clarify)) +
      settingRow('Capitalization', 'Capitalize transcripts automatically', toggleHtml('set-auto_capitalization', cfg.auto_capitalization !== false)) +
      settingRow('Punctuation', 'Keep punctuation from speech recognition', toggleHtml('set-auto_punctuation', cfg.auto_punctuation !== false)) +
      settingRow('Training corrections', 'Apply words and triggers from the Train tab', toggleHtml('set-training_corrections', cfg.training_corrections !== false)) +
      settingRow('Word-count threshold', 'Use the long model above this number of words', `<input type="number" id="set-word_count_threshold" min="1" max="500" value="${escapeHtml(cfg.word_count_threshold)}">`) +
      settingRow('Push-to-talk hotkey', 'Hold to record', `<input type="text" class="hotkey-input" id="hk-push_to_talk" value="${escapeHtml(hk.push_to_talk || '')}" spellcheck="false">`) +
      settingRow('Toggle hotkey', 'Press once to start or stop', `<input type="text" class="hotkey-input" id="hk-toggle" value="${escapeHtml(hk.toggle || '')}" spellcheck="false">`) +
      settingRow('Clarify hotkey', 'Polish selected text or clipboard', `<input type="text" class="hotkey-input" id="hk-clarify" value="${escapeHtml(hk.clarify || '')}" spellcheck="false">`) +
      settingRow('Learn correction hotkey', 'Select corrected text after dictation', `<input type="text" class="hotkey-input" id="hk-learn_correction" value="${escapeHtml(hk.learn_correction || '')}" spellcheck="false">`) +
      settingRow('Logging', 'Write diagnostic logs to disk', toggleHtml('set-logging', cfg.logging)) +
      settingRow('Developer mode', 'Enable extra diagnostics', toggleHtml('set-developer_mode', cfg.developer_mode)) +
      `<div class="settings-actions"><button class="btn" id="resetStatsBtn">Reset statistics</button></div>`;

    wireSettingControls();
  } catch (e) {
    list.innerHTML = '<div class="empty-hint">Settings unavailable while the backend starts.</div>';
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
  patchToggle('set-auto_capitalization', 'auto_capitalization');
  patchToggle('set-auto_punctuation', 'auto_punctuation');
  patchToggle('set-training_corrections', 'training_corrections');
  patchToggle('set-logging', 'logging');
  patchToggle('set-developer_mode', 'developer_mode');

  $('#set-microphone').addEventListener('change', (e) => saveSetting('microphone', e.target.value || null));
  $('#set-theme').addEventListener('change', (e) => {
    applyTheme(e.target.value);
    saveSetting('theme', e.target.value);
  });

  const threshold = $('#set-word_count_threshold');
  threshold.addEventListener('change', () => {
    saveSetting('word_count_threshold', parseInt(threshold.value, 10) || 100);
  });

  ['push_to_talk', 'toggle', 'clarify', 'learn_correction'].forEach((k) => {
    const el = $('#hk-' + k);
    el.addEventListener('change', saveHotkeys);
  });

  $('#resetStatsBtn').addEventListener('click', async () => {
    await window.afk.call('reset_statistics', {});
    refreshStatistics();
  });
}

async function saveSetting(key, value) {
  try {
    const updated = await window.afk.call('update_settings', { patch: { [key]: value } });
    _settingsCache = updated;
    refreshHotkeys();
  } catch (e) {
    // Settings writes are best-effort during backend startup.
  }
}

async function saveHotkeys() {
  const hotkeys = {
    push_to_talk: $('#hk-push_to_talk').value.trim(),
    toggle: $('#hk-toggle').value.trim(),
    clarify: $('#hk-clarify').value.trim(),
    learn_correction: $('#hk-learn_correction').value.trim()
  };
  try {
    const updated = await window.afk.call('set_hotkeys', { hotkeys });
    _settingsCache = { ...(_settingsCache || {}), hotkeys: updated };
    refreshHotkeys();
  } catch (e) {
    $('#clarifyMeta').textContent = 'Hotkey save failed';
  }
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
        $('#recordStatus').textContent = 'Transcribing...';
        break;
      case 'transcription':
        showTranscription(data && data.text, data && data.message);
        $('#recordStatus').textContent = 'Idle';
        refreshAsrStatus();
        refreshHomeStats();
        break;
      case 'clarify_done':
        if (data && data.text) {
          $('#clarifyOutput').textContent = data.text;
          $('#clarifyMeta').textContent = `${data.model || ''}` +
            (data.latency_ms ? ` / ${data.latency_ms} ms` : '');
        }
        refreshClarifyStatus();
        break;
      case 'statistics_updated':
        if ($('#page-statistics').classList.contains('active')) refreshStatistics();
        refreshHomeStats();
        break;
      case 'correction_learned':
        $('#recordStatus').textContent = data && data.ok ? 'Learned correction' : 'Learning skipped';
        refreshTrain();
        refreshHomeStats();
        break;
      case 'training_sample_saved':
        if ($('#page-train').classList.contains('active')) refreshTrain();
        refreshHomeStats();
        break;
      case 'adaptation_updated':
        if ($('#page-train').classList.contains('active')) refreshTrain();
        refreshHomeStats();
        break;
      default:
        break;
    }
  });
}

function setRecording(on) {
  const orb = $('#recordOrb');
  const status = $('#recordStatus');
  const btn = $('#recordBtn');
  isRecording = on;
  orb.classList.toggle('recording', on);
  status.textContent = on ? 'Recording' : 'Idle';
  btn.classList.toggle('recording', on);
  btn.textContent = on ? 'Stop and transcribe' : 'Start recording';
  btn.disabled = false;
  if (!on && activeTrainingKind) {
    const status = activeTrainingKind === 'trigger' ? $('#trainTriggerStatus') : $('#trainWordStatus');
    if (status) status.textContent = 'Recording stopped. Finish to save this sample.';
  }

  if (on) {
    recStart = Date.now();
    clearInterval(recTimer);
    recTimer = setInterval(() => {
      const s = Math.floor((Date.now() - recStart) / 1000);
      const mm = String(Math.floor(s / 60)).padStart(2, '0');
      const ss = String(s % 60).padStart(2, '0');
      $('#recordTimer').textContent = `${mm}:${ss}`;
    }, 250);
  } else {
    clearInterval(recTimer);
    recTimer = null;
  }
}

async function copyTranscript(text) {
  if (!text) return;
  try {
    await window.afk.call('set_clipboard', { text });
    $('#recordStatus').textContent = 'Copied';
  } catch (e) {
    $('#recordStatus').textContent = 'Idle';
  }
}

function showTranscription(text, message) {
  const el = $('#transcription');
  if (text && message) el.textContent = `${text}\n\n${message}`;
  else if (text) el.textContent = text;
  else if (message) el.textContent = message;
}

// ---------- Boot ----------
window.addEventListener('DOMContentLoaded', async () => {
  initNav();
  initEvents();
  initEditableHotkeyHandling();
  initTrainControls();
  $('#recordBtn').addEventListener('click', toggleRecord);
  $('#loadAsrBtn').addEventListener('click', loadAsrModel);
  $('#micSelect').addEventListener('change', onMicChange);
  $('#clarifyBtn').addEventListener('click', clarifyText);

  await initAbout();
  await applySavedTheme();
  await refreshBackendInfo();
  await refreshHotkeys();
  await refreshMicrophones();
  await refreshAsrStatus();
  await refreshClarifyStatus();
  await refreshHomeStats();
  await refreshTrain();

  setTimeout(() => {
    refreshBackendInfo();
    refreshAsrStatus();
    refreshClarifyStatus();
  }, 1500);

  const poll = setInterval(() => {
    refreshAsrStatus();
    refreshClarifyStatus();
  }, 2500);
  setTimeout(() => clearInterval(poll), 90000);
});
