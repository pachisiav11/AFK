'use strict';

const bar = document.getElementById('bar');
const label = document.getElementById('label');
const sub = document.getElementById('sub');

const copy = {
  recording: ['Listening', 'AFK is capturing your voice'],
  processing: ['Transcribing', 'Turning speech into text'],
  done: ['Done', 'Ready']
};

window.afk.onOverlayState((payload) => {
  const state = payload && payload.state ? payload.state : 'recording';
  const fallback = copy[state] || copy.recording;
  bar.dataset.state = state;
  label.textContent = payload.label || fallback[0];
  sub.textContent = payload.sub || fallback[1];
});
