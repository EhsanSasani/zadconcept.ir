import test from "node:test";
import assert from "node:assert/strict";

import { installDom } from "./dom-helpers.mjs";

test("product dialog opens from an enhanced link and restores focus on Escape", async () => {
  const cleanup = installDom(`
    <main data-background>
      <article data-catalog-card data-product-code="Z1" data-product-name="Rose" data-product-price="100" data-product-type="box">
        <a href="/flowers/box/z1/" data-zad-modal-card><img src="/rose.jpg" alt="Rose" data-product-image></a>
      </article>
    </main>
    <aside inert data-existing-inert></aside>
    <div data-product-modal hidden>
      <div data-product-modal-close></div>
      <div role="dialog" tabindex="-1">
        <button data-product-modal-close data-product-modal-close-button>Close</button>
        <img data-modal-image><span data-modal-type></span><h2 data-modal-title></h2>
        <p data-modal-price></p><p data-modal-description></p><p data-modal-stock></p><p data-modal-contact></p>
      </div>
    </div>
  `);
  await import(`../../main/static/main/js/components/product-dialog.js?test=${Date.now()}`);

  const opener = document.querySelector("[data-zad-modal-card]");
  const modal = document.querySelector("[data-product-modal]");
  const background = document.querySelector("[data-background]");
  document.body.style.overflow = "clip";
  opener.focus();
  opener.click();

  assert.equal(modal.hidden, false);
  assert.equal(background.hasAttribute("inert"), true);
  assert.equal(document.body.classList.contains("has-open-product-dialog"), true);
  assert.equal(document.body.style.overflow, "hidden");
  assert.equal(document.querySelector("[data-modal-title]").textContent, "Rose");
  assert.equal(document.activeElement, document.querySelector("[data-product-modal-close-button]"));

  document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  assert.equal(modal.hidden, true);
  assert.equal(background.hasAttribute("inert"), false);
  assert.equal(document.querySelector("[data-existing-inert]").hasAttribute("inert"), true);
  assert.equal(document.body.classList.contains("has-open-product-dialog"), false);
  assert.equal(document.body.style.overflow, "clip");
  assert.equal(document.activeElement, opener);
  cleanup();
});

test("product dialog leaves modified link clicks to the browser", async () => {
  const cleanup = installDom(`
    <a href="/flowers/box/z1/" data-zad-modal-card>Rose</a>
    <div data-product-modal hidden>
      <div role="dialog" tabindex="-1"><button data-product-modal-close-button>Close</button></div>
    </div>
  `);
  await import(`../../main/static/main/js/components/product-dialog.js?modified=${Date.now()}`);

  const opener = document.querySelector("[data-zad-modal-card]");
  const event = new window.MouseEvent("click", {
    bubbles: true,
    cancelable: true,
    ctrlKey: true,
  });
  opener.dispatchEvent(event);

  assert.equal(event.defaultPrevented, false);
  assert.equal(document.querySelector("[data-product-modal]").hidden, true);
  cleanup();
});
