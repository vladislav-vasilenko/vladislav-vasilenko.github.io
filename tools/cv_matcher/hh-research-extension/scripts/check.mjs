/* No npm dependencies; usable locally and in CI. */
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {extensionRoot} from './build-adapters.mjs';

function run(args) {
  const result=spawnSync(process.execPath,args,{cwd:extensionRoot,stdio:'inherit'});
  if(result.error)throw result.error;
  if(result.status!==0)process.exit(result.status||1);
}
function scripts(directory) {
  return fs.readdirSync(directory,{withFileTypes:true}).flatMap(entry=>{
    const file=path.join(directory,entry.name);
    return entry.isDirectory() ? (['adapters','scripts'].includes(entry.name)?scripts(file):[]) : /\.(?:js|mjs)$/.test(entry.name)?[file]:[];
  });
}
run(['scripts/build-adapters.mjs','--check']);
for(const file of scripts(extensionRoot))run(['--check',file]);
run(['--test',...fs.readdirSync(extensionRoot).filter(name=>name.endsWith('.test.mjs')).sort()]);
