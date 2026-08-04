import test from "node:test";
import assert from "node:assert/strict";

import { initNavigation } from "../../main/static/main/js/components/navigation.js";
import { installDom } from "./dom-helpers.mjs";

test("navigation disclosure closes with Escape and restores trigger focus", () => {
  const cleanup = installDom(`
    <header data-site-header></header>
    <details data-nav-dropdown>
      <summary data-nav-dropdown-trigger>Products</summary>
      <div data-nav-dropdown-menu><a href="/flowers/">Flowers</a></div>
    </details>
  `);
  initNavigation();

  const dropdown = document.querySelector("[data-nav-dropdown]");
  const trigger = document.querySelector("[data-nav-dropdown-trigger]");
  trigger.click();
  assert.equal(dropdown.open, true);
  assert.equal(trigger.getAttribute("aria-expanded"), "true");

  dropdown.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  assert.equal(dropdown.open, false);
  assert.equal(trigger.getAttribute("aria-expanded"), "false");
  assert.equal(document.activeElement, trigger);
  cleanup();
});
