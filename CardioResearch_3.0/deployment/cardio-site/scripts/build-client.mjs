import fs from 'node:fs/promises';
import path from 'node:path';
import {spawnSync} from 'node:child_process';

const root = process.cwd();
const client = path.join(root, 'client');
for (const [script, args] of [['typescript/bin/tsc', ['-b']], ['vite/bin/vite.js', ['build']]]) {
  const result = spawnSync(process.execPath, [path.join(client, 'node_modules', script), ...args], {cwd: client, stdio: 'inherit'});
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error('Client build failed: ' + script);
}
// public/assets is generated solely by the client build.
const source = path.join(client, 'dist');
const output = path.join(root, 'public');
await fs.access(path.join(source, 'index.html'));
const assets = path.resolve(output, 'assets');
if (assets !== path.join(path.resolve(root), 'public', 'assets')) throw new Error('Unexpected assets path');
await fs.rm(assets, {recursive: true, force: true});
await fs.cp(source, output, {recursive: true});
