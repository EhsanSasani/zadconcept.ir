import test from "node:test";
import assert from "node:assert/strict";

import { initNavigation } from "../../main/static/main/js/components/navigation.js";
import { installDom } from "./dom-helpers.mjs";

test("navigation disclosure closes with Escape and restores trigger focus", () => {
  const cleanup = installDom(`
    <header data-site-header></header>
    <div class="main-nav__center">
      <details data-nav-dropdown>
        <summary data-nav-dropdown-trigger>Products</summary>
        <div data-nav-dropdown-menu><a href="/flowers/">Flowers</a></div>
      </details>
    </div>
  `);
  initNavigation();

  const dropdown = document.querySelector("[data-nav-dropdown]");
  const trigger = document.querySelector("[data-nav-dropdown-trigger]");
  const center = document.querySelector(".main-nav__center");
  trigger.click();
  assert.equal(dropdown.open, true);
  assert.equal(center.classList.contains("has-open-dropdown"), true);
  assert.equal(trigger.getAttribute("aria-expanded"), "true");

  dropdown.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  assert.equal(dropdown.open, false);
  assert.equal(center.classList.contains("has-open-dropdown"), false);
  assert.equal(trigger.getAttribute("aria-expanded"), "false");
  assert.equal(document.activeElement, trigger);
  cleanup();
});
