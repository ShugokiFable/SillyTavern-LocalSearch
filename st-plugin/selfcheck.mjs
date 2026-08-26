// One runnable check for index.mjs: start -> real search -> stop -> port released.
// Run:  node st-plugin/selfcheck.mjs
import assert from 'node:assert/strict';

const PORT = Number(process.env.LOCAL_SEARCH_PORT) || 18888;
const base = `http://127.0.0.1:${PORT}`;
const up = async () => { try { await fetch(base + '/', { signal: AbortSignal.timeout(1500) }); return true; } catch { return false; } };

assert.equal(await up(), false, `something is already on ${PORT}; stop it before running this`);

const p = await import('./index.mjs');
assert.equal(p.info.id, 'local-search');

await p.init();
await new Promise(r => setTimeout(r, 2500));
assert.equal(await up(), true, 'init() did not bring the search endpoint up');

const html = await (await fetch(`${base}/search?q=sillytavern`)).text();
const links = [...html.matchAll(/class="url_wrapper" href="/g)].length;
assert.ok(links > 0, 'search returned no links (DuckDuckGo rate limit? try again in a minute)');

await p.exit();
await new Promise(r => setTimeout(r, 800));
assert.equal(await up(), false, 'exit() left the process running');

console.log(`ok - started, ${links} links, stopped cleanly`);
