#!/usr/bin/env node
/** Explicit entry points for two projects; no secrets, sync or model calls. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'workspace.projects.json'), 'utf8'));
const [project = 'list', command = ''] = process.argv.slice(2);

function run(executable, args, cwd) {
  const result = spawnSync(executable, args, {cwd, stdio: 'inherit', shell: false});
  if (result.error) {
    process.stderr.write(result.error.message + '\n');
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status || 1);
}

if (project === 'list') {
  for (const [id, entry] of Object.entries(manifest.projects)) {
    process.stdout.write(`${id}: ${entry.label}\n  ${entry.root} → ${entry.local_url}\n`);
  }
  process.exit(0);
}

if (project === 'check') {
  for (const [id, entry] of Object.entries(manifest.projects)) {
    const directory = path.resolve(root, entry.root);
    if (directory !== root && !directory.startsWith(root + path.sep)) {
      throw Error('Project escapes workspace: ' + id);
    }
    for (const key of ['entry', 'source', 'content', 'web', 'extension']) {
      if (entry[key] && !fs.existsSync(path.join(directory, entry[key]))) {
        throw Error(`Missing ${id}.${key}: ${entry[key]}`);
      }
    }
    if (!fs.existsSync(path.join(root, entry.docs))) {
      throw Error('Missing project docs: ' + entry.docs);
    }
  }
  process.stdout.write('Workspace project boundaries and entry points: OK\n');
  process.exit(0);
}

const entry = manifest.projects[project];
if (!entry) throw Error('Choose portfolio or career; use list for project paths.');
const cwd = path.resolve(root, entry.root);

if (project === 'portfolio') {
  const vite = path.join(root, 'node_modules/vite/bin/vite.js');
  const tsc = path.join(root, 'node_modules/typescript/bin/tsc');
  if (command === 'build') {
    run(process.execPath, [tsc], cwd);
    run(process.execPath, [vite, 'build'], cwd);
  } else if (command === 'dev') {
    const url = new URL(entry.local_url);
    run(process.execPath, [vite, '--host', url.hostname, '--port', url.port, '--strictPort'], cwd);
  } else if (command === 'preview') {
    run(process.execPath, [vite, 'preview'], cwd);
  } else {
    throw Error('Portfolio: dev, build, preview');
  }
} else {
  const python = path.join(cwd, '.venv/bin/python');
  if (!fs.existsSync(python)) throw Error('Run uv sync in tools/cv_matcher first.');
  if (command === 'dev') run(python, [entry.entry], cwd);
  else if (command === 'test') run(python, ['scripts/test-isolated.py'], cwd);
  else if (command === 'check') run(process.execPath, ['hh-research-extension/scripts/check.mjs'], cwd);
  else throw Error('Career: dev, test, check');
}
