/* No npm dependencies; usable locally and in CI. Covers the extension and the
 * local web UI in ../archive-web: syntax of every script and both test sets. */
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {extensionRoot} from './build-adapters.mjs';

const webRoot=path.resolve(extensionRoot,'..','archive-web');

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
function tests(directory) {
  return fs.readdirSync(directory).filter(name=>name.endsWith('.test.mjs')).sort().map(name=>path.join(directory,name));
}
run(['scripts/build-adapters.mjs','--check']);
for(const file of scripts(extensionRoot))run(['--check',file]);
for(const file of fs.readdirSync(webRoot).filter(name=>name.endsWith('.js')))run(['--check',path.join(webRoot,file)]);
run(['--test',...tests(extensionRoot),...tests(path.join(webRoot,'tests'))]);
