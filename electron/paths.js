'use strict';

const path = require('path');
const fs = require('fs');
const { app } = require('electron');

/**
 * Centralised filesystem locations for AFK.
 * User data lives in the OS app-data dir so it survives reinstalls/updates.
 */
function dataDir() {
  const dir = path.join(app.getPath('userData'), 'data');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function logsDir() {
  const dir = path.join(app.getPath('userData'), 'logs');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function modelsDir() {
  // Models are large and downloaded on first run; keep them in userData by
  // default so they are not wiped on app update.
  const dir = path.join(app.getPath('userData'), 'models');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

module.exports = { dataDir, logsDir, modelsDir };
