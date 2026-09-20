import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const source = readFileSync(new URL('../../main/static/main/js/core/analytics.js', import.meta.url), 'utf8');
function run(sameDay, withGtag) {
  const events = [], handlers = {};
  const window = { dataLayer: [] };
  if (withGtag) window.gtag = (type, name, data) => events.push({ event: name, ...data });
  const document = {
    referrer: '',
    body: { dataset: { pageType: 'catalog' }, classList: { contains: name => sameDay && name === 'page-same-day' } },
    querySelector: () => null, querySelectorAll: () => [],
    addEventListener: (name, callback) => { handlers[name] = callback; },
  };
  vm.runInNewContext(source, { window, document });
  const click = href => handlers.click({ target: { closest: () => ({
    dataset: { ctaPosition: 'same_day_guide' }, getAttribute: () => href, closest: () => null,
  }) } });
  click('tel:+985100000000');
  click('https://t.me/example');
  return withGtag ? events : window.dataLayer;
}
for (const withGtag of [true,false]) {
  test(`same-day events are attributed once (gtag=${withGtag})`, () => {
    const events = run(true,withGtag);
    assert.deepEqual(events.map(e => e.event), ['zad_page_view','click_to_call','click_telegram']);
    assert.ok(events.every(e => e.page_type === 'same_day'));
    assert.equal(events[1].cta_position,'same_day_guide');
  });
}
test('general catalog attribution is preserved', () => {
  assert.ok(run(false,true).every(e => e.page_type === 'catalog'));
});
