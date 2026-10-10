// Parse actual Mermaid syntax without rendering or fetching document URLs.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';

if (!process.argv[2]) throw new Error('Pass the isolated npm dependency directory');
const dependencies = resolve(process.argv[2], 'node_modules');
const { JSDOM } = await import(pathToFileURL(resolve(dependencies, 'jsdom/lib/api.js')));
const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.window = dom.window;
globalThis.document = dom.window.document;
const { default: mermaid } = await import(pathToFileURL(resolve(dependencies, 'mermaid/dist/mermaid.core.mjs')));
mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
const files = [...new Set(execFileSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard'], { encoding: 'utf8' }).split('\0').filter(Boolean))];
let count = 0;
for (const file of files) {
  if (!file.endsWith('.md') && !file.endsWith('.mmd')) continue;
  const text = readFileSync(file, 'utf8');
  const diagrams = file.endsWith('.mmd') ? [text] : [];
  if (file.endsWith('.md')) {
    let fence = null, language = '', body = [];
    for (const line of text.split(/\r?\n/)) {
      const match = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
      if (!fence && match) {
        fence = match[1]; language = match[2].trim(); body = [];
      } else if (fence && new RegExp('^ {0,3}' + fence[0] + '{' + fence.length + ',}\\s*$').test(line)) {
        if (language === 'mermaid') diagrams.push(body.join('\n'));
        fence = null;
      } else if (fence) body.push(line);
    }
    if (fence) throw new Error(`${file}: unclosed code fence`);
  }
  for (const diagram of diagrams) {
    try { await mermaid.parse(diagram); }
    catch (error) { throw new Error(`${file}: ${error.message}`); }
    count += 1;
  }
}
if (!count) throw new Error('No Mermaid diagrams discovered');
// Prove that parsing rejects malformed syntax rather than silently accepting it.
let rejected = false;
try { await mermaid.parse('flowchart LR\nA --> ['); } catch { rejected = true; }
if (!rejected) throw new Error('Mermaid negative control was accepted');
console.log(`Mermaid parser: ${count} diagrams passed; malformed negative control rejected`);
dom.window.close();
