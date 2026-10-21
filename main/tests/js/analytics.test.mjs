import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const script = readFileSync(new URL('../../static/main/js/core/analytics.js', import.meta.url), 'utf8');
const key = 'zad_ai_source_v1';
function run({referrer = '', url = 'https://www.zadconcept.ir/', storage = new Map(), blocked = false, gtag = false, item = false} = {}) {
  const events = [], handlers = {};
  const window = {location: {href: url}, dataLayer: [], sessionStorage: {
    getItem(k) {if (blocked) throw Error('blocked'); return storage.get(k);},
    setItem(k, v) {if (blocked) throw Error('blocked'); storage.set(k, v);},
    removeItem(k) {if (blocked) throw Error('blocked'); storage.delete(k);},
  }};
  if (gtag) window.gtag = (_, event, params) => events.push({event, ...params});
  const document = {referrer, body: {dataset: item ? {itemId: 'ST-1'} : {}, classList: {contains: () => false}},
    querySelector: () => null, querySelectorAll: () => [], addEventListener: (name, fn) => {handlers[name] = fn;}};
  vm.runInNewContext(script, {window, document, URL, Date});
  return {events: gtag ? events : window.dataLayer, storage, click(href) {
    const link = {dataset: {}, getAttribute: () => href, closest: () => null};
    handlers.click({target: {closest: () => link}});
  }};
}

for (const [host, source] of Object.entries({'chatgpt.com': 'chatgpt', 'www.perplexity.ai': 'perplexity', 'claude.ai': 'claude', 'gemini.google.com': 'gemini', 'copilot.microsoft.com': 'copilot'})) {
  test(`attributes ${source} to page, product and contact events`, () => {
    const result = run({referrer: `https://${host}/private-prompt?token=secret`, item: true, gtag: true});
    result.click('tel:123');
    assert.equal(result.events.length, 3);
    assert.ok(result.events.every(e => e.ai_source === source && e.traffic_source === source));
    assert.ok(!JSON.stringify([...result.storage]).includes('secret'));
  });
}
test('UTM source works without a referrer and survives internal navigation', () => {
  const first = run({url: 'https://www.zadconcept.ir/?utm_source=chatgpt.com'});
  const next = run({storage: first.storage, referrer: 'https://www.zadconcept.ir/'});
  next.click('https://t.me/zad');
  assert.equal(next.events.at(-1).ai_source, 'chatgpt');
});
test('external campaigns and external non-AI referrers clear previous attribution', () => {
  for (const options of [{url: 'https://www.zadconcept.ir/?utm_source=newsletter'}, {referrer: 'https://google.com/'}]) {
    const storage = run({referrer: 'https://chatgpt.com/'}).storage;
    assert.equal(run({...options, storage}).events[0].ai_source, null);
    assert.equal(storage.has(key), false);
  }
});
test('hostname spoofing and URL text do not count as AI referrals', () => {
  for (const referrer of ['https://chatgpt.com.example.org/', 'https://example.org/chatgpt.com', 'https://example.org/?q=claude.ai']) {
    assert.equal(run({referrer}).events[0].ai_source, null);
  }
});
test('expired, malformed and future session data are discarded', () => {
  for (const value of ['broken', JSON.stringify({source: 'chatgpt', at: Date.now() - 1800001}), JSON.stringify({source: 'chatgpt', at: Date.now() + 60000})]) {
    const storage = new Map([[key, value]]);
    assert.equal(run({storage}).events[0].ai_source, null);
    assert.equal(storage.has(key), false);
  }
});
test('blocked storage does not prevent page or contact events', () => {
  const result = run({blocked: true, referrer: 'https://claude.ai/'});
  result.click('tel:123');
  assert.equal(result.events.at(-1).ai_source, 'claude');
});
