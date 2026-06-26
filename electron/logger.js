'use strict';

const fs = require('fs');
const path = require('path');

/**
 * Tiny file + console logger. No external deps so it works before the
 * backend is up. Levels: debug < info < warn < error.
 */
const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };

class Logger {
  constructor() {
    this.stream = null;
    this.minLevel = LEVELS.info;
    this.devMode = !!process.env.AFK_DEV;
    if (this.devMode) this.minLevel = LEVELS.debug;
  }

  init(logsDir) {
    try {
      const file = path.join(logsDir, `afk-${new Date().toISOString().slice(0, 10)}.log`);
      this.stream = fs.createWriteStream(file, { flags: 'a' });
    } catch (e) {
      // logging must never crash the app
    }
  }

  setLevel(level) {
    if (LEVELS[level]) this.minLevel = LEVELS[level];
  }

  _write(level, msg) {
    if (LEVELS[level] < this.minLevel) return;
    const line = `${new Date().toISOString()} [${level.toUpperCase()}] ${msg}`;
    if (this.devMode || level === 'error') {
      // eslint-disable-next-line no-console
      console[level === 'debug' ? 'log' : level](line);
    }
    if (this.stream) {
      try { this.stream.write(line + '\n'); } catch (_) { /* ignore */ }
    }
  }

  debug(msg) { this._write('debug', msg); }
  info(msg) { this._write('info', msg); }
  warn(msg) { this._write('warn', msg); }
  error(msg) { this._write('error', msg); }
}

module.exports = new Logger();
