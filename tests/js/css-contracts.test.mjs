import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { installDom } from "./dom-helpers.mjs";

test("hidden rail controls stay hidden in the production stylesheet order", () => {
  const cleanup = installDom(
    '<button class="featured-products__nav" hidden>Next</button>',
  );
  const styles = ["utilities.css", "catalog.css", "responsive.css"]
    .map((fileName) => {
      return readFileSync(`main/static/main/css/${fileName}`, "utf8");
    })
    .join("\n");
  const style = document.createElement("style");
  style.textContent = styles;
  document.head.append(style);

  const control = document.querySelector(".featured-products__nav");
  assert.equal(control.hidden, true);
  assert.equal(window.getComputedStyle(control).display, "none");
  cleanup();
});
