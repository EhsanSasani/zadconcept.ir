const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const vm = require("node:vm");

const source = readFileSync(join(__dirname, "../static/main/js/pages/home/moments-rail.js"), "utf8");

// Behavioral harness; actual touch/sticky rendering needs device verification.
function harness({ count = 6, reduced = false, missing = false } = {}) {
  const callbacks = {};
  const document = { readyState: "complete", activeElement: null };
  const items = Array.from({ length: count }, () => ({
    focus() { document.activeElement = this; },
    scrollIntoView(options) { this.scrollOptions = options; },
  }));
  const track = {
    addEventListener(event, callback) { callbacks[event] = callback; },
    querySelectorAll() { return items; },
  };
  const rail = { querySelector(selector) {
    assert.equal(selector, "[data-moments-track]");
    return missing ? null : track;
  } };
  document.querySelectorAll = () => [rail];
  vm.runInNewContext(source, {
    document,
    window: { matchMedia: () => ({ matches: reduced }) },
  });
  return { callbacks, items, document };
}

test("works without rail arrow buttons or a resize/scroll handler", () => {
  const h = harness();
  assert.deepEqual(Object.keys(h.callbacks), ["keydown"]);
});
test("arrow keys move focus left-to-right", () => {
  const h = harness();
  h.document.activeElement = h.items[0];
  let prevented = false;
  h.callbacks.keydown({ key: "ArrowRight", preventDefault() { prevented = true; } });
  assert.equal(h.document.activeElement, h.items[1]);
  assert.equal(h.items[1].scrollOptions.behavior, "smooth");
  assert.equal(prevented, true);
  h.callbacks.keydown({ key: "ArrowLeft", preventDefault() {} });
  assert.equal(h.document.activeElement, h.items[0]);
});
test("reduced motion scrolls focused covers instantly", () => {
  const h = harness({ reduced: true });
  h.document.activeElement = h.items[0];
  h.callbacks.keydown({ key: "ArrowRight", preventDefault() {} });
  assert.equal(h.items[1].scrollOptions.behavior, "instant");
});
test("native Enter, Space, Tab and modified arrows stay untouched", () => {
  const h = harness(); h.document.activeElement = h.items[0];
  for (const key of ["Enter", " ", "Tab"]) {
    h.callbacks.keydown({ key, preventDefault() { assert.fail("Native key intercepted"); } });
  }
  h.callbacks.keydown({ key: "ArrowRight", ctrlKey: true, preventDefault() { assert.fail("Modified key intercepted"); } });
  assert.equal(h.document.activeElement, h.items[0]);
});
test("ends do not wrap or steal focus", () => {
  const h = harness();
  h.document.activeElement = h.items[0];
  h.callbacks.keydown({ key: "ArrowLeft", preventDefault() { assert.fail(); } });
  h.document.activeElement = h.items[5];
  h.callbacks.keydown({ key: "ArrowRight", preventDefault() { assert.fail(); } });
  assert.equal(h.document.activeElement, h.items[5]);
});
test("empty, single and twelve-highlight rails initialize safely", () => {
  for (const count of [0, 1, 12]) assert.doesNotThrow(() => harness({ count }));
  assert.doesNotThrow(() => harness({ missing: true }));
});
test("arrow elements are gone, viewer navigation is retained", () => {
  const template = readFileSync(join(__dirname, "../templates/main/components/story_rail.html"), "utf8");
  assert.ok(!template.includes("data-moments-next"));
  assert.ok(!template.includes("data-moments-previous"));
  assert.ok(template.includes("data-story-next"));
  assert.ok(template.includes("data-story-previous"));
});
test("mobile cover override only changes positioning and opacity, not hero geometry", () => {
  const css = readFileSync(join(__dirname, "../static/main/css/pages/home/moments-discover.css"), "utf8");
  const fix = css.slice(css.indexOf("/* Mobile uses the same native"));
  assert.ok(fix.includes("@media (max-width: 760px)"));
  assert.ok(fix.includes("section.home-hero"));
  assert.ok(fix.includes("position: sticky !important"));
  assert.ok(fix.includes(".home-hero ~ .home-section"));
  assert.ok(!/(?:^|\n)\s*(?:height|width|aspect-ratio|object-fit|object-position)\s*:/.test(fix));
});
