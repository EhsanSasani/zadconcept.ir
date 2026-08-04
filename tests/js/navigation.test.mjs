import test from "node:test";
import assert from "node:assert/strict";

import { initNavigation } from "../../main/static/main/js/components/navigation.js";
import { installDom } from "./dom-helpers.mjs";

test("navigation disclosure closes with Escape and restores trigger focus", () => {
  const cleanup = installDom(`
    <header data-site-header></header>
    <div data-nav-dropdown>
      <button data-nav-dropdown-trigger aria-expanded="false">Products</button>
      <div data-nav-dropdown-menu><a href="/flowers/">Flowers</a></div>
    </div>
  `);
  initNavigation();

  const dropdown = document.querySelector("[data-nav-dropdown]");
  const trigger = document.querySelector("[data-nav-dropdown-trigger]");
  trigger.click();
  assert.equal(trigger.getAttribute("aria-expanded"), "true");

  dropdown.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  assert.equal(trigger.getAttribute("aria-expanded"), "false");
  assert.equal(document.activeElement, trigger);
  cleanup();
});
