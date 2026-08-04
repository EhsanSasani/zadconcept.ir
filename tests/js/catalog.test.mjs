import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "./dom-helpers.mjs";

test("catalog exposes busy, current-filter, and result-count states", async () => {
  const cleanup = installDom(`
    <nav data-catalog-filter>
      <a href="/bakery/" data-filter="all" aria-current="page">All</a>
      <a href="/bakery/?category=cake" data-filter="cake">Cake</a>
    </nav>
    <div data-catalog-grid aria-busy="false"><article>Old</article></div>
    <div data-catalog-loader data-load-url="/bakery/" data-next-page="" data-has-next="false">
      <span data-catalog-loader-status></span>
      <button data-catalog-load-more hidden></button>
    </div>
  `);
  window.scrollTo = () => {};
  let resolveRequest;
  globalThis.fetch = () => {
    return new Promise((resolve) => {
      resolveRequest = resolve;
    });
  };
  await import(`../../main/static/main/js/pages/catalog.js?state=${Date.now()}`);

  const cake = document.querySelector('[data-filter="cake"]');
  cake.click();
  await Promise.resolve();

  const grid = document.querySelector("[data-catalog-grid]");
  const loader = document.querySelector("[data-catalog-loader]");
  assert.equal(grid.getAttribute("aria-busy"), "true");
  assert.equal(loader.getAttribute("aria-busy"), "true");

  resolveRequest({
    ok: true,
    json: async () => ({
      html: "<article>Fresh</article>",
      has_next: false,
      next_page: null,
      page_count: 1,
      total_count: 12,
    }),
  });
  await new Promise((resolve) => {
    setTimeout(resolve, 0);
  });

  assert.equal(grid.textContent, "Fresh");
  assert.equal(grid.getAttribute("aria-busy"), "false");
  assert.equal(loader.getAttribute("aria-busy"), "false");
  assert.equal(cake.getAttribute("aria-current"), "page");
  assert.equal(document.querySelector('[data-filter="all"]').hasAttribute("aria-current"), false);
  assert.equal(
    document.querySelector("[data-catalog-loader-status]").textContent,
    "12 محصول پیدا شد؛ 1 محصول نمایش داده شد.",
  );

  delete globalThis.fetch;
  cleanup();
});
