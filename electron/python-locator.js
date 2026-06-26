'use strict';

/**
 * Locates the Python interpreter and backend entry point in both
 * development and packaged (production) environments.
 *
 * Dev:
 *   - Prefer python/.venv (created by `npm run setup:python`)
 *   - Fall back to the Windows `py -3.11` launcher, then `python`
 *   Backend entry: <repo>/python/main.py
 *
 * Production (packaged):
 *   - Bundled interpreter at resources/python/.venv (or resources/python/runtime)
 *   Backend entry: resources/python/main.py
 */

const path = require('path');
const fs = require('fs');

function isPackaged() {
  // app.isPackaged is the source of truth, but this module is also used by
  // tests without electron loaded. Detect via resourcesPath presence.
  try {
    const { app } = require('electron');
    return app.isPackaged;
  } catch (_) {
    return false;
  }
}

function pythonRoot() {
  if (isPackaged()) {
    return path.join(process.resourcesPath, 'python');
  }
  return path.join(__dirname, '..', 'python');
}

function backendEntry() {
  return path.join(pythonRoot(), 'main.py');
}

function exists(p) {
  try {
    return fs.existsSync(p);
  } catch (_) {
    return false;
  }
}

/**
 * Resolve the python command + leading args.
 * @returns {{ command: string, args: string[] }}
 */
function resolvePython() {
  const root = pythonRoot();

  // 1. Bundled / project virtual environment.
  const venvPythonWin = path.join(root, '.venv', 'Scripts', 'python.exe');
  const venvPythonNix = path.join(root, '.venv', 'bin', 'python');
  if (exists(venvPythonWin)) return { command: venvPythonWin, args: [] };
  if (exists(venvPythonNix)) return { command: venvPythonNix, args: [] };

  // 2. Embedded runtime shipped with the installer.
  const runtimeWin = path.join(root, 'runtime', 'python.exe');
  if (exists(runtimeWin)) return { command: runtimeWin, args: [] };

  // 3. Windows launcher pinned to 3.11 (dev fallback).
  if (process.platform === 'win32') {
    return { command: 'py', args: ['-3.11'] };
  }

  // 4. Generic fallback.
  return { command: 'python3', args: [] };
}

module.exports = { resolvePython, backendEntry, pythonRoot, isPackaged };
