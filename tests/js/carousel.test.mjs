import test from "node:test";
import assert from "node:assert/strict";

import { wrapIndex } from "../../main/static/main/js/core/carousel.js";
import { createCarousel } from "../../main/static/main/js/core/carousel.js";
import { logicalScrollDelta } from "../../main/static/main/js/core/direction.js";
import { installDom } from "./dom-helpers.mjs";

test("wrapIndex wraps carousel indexes in both directions", () => {
  assert.equal(wrapIndex(0, 4), 0);
  assert.equal(wrapIndex(4, 4), 0);
  assert.equal(wrapIndex(5, 4), 1);
  assert.equal(wrapIndex(-1, 4), 3);
  assert.equal(wrapIndex(-5, 4), 3);
});

test("wrapIndex is safe for an empty collection", () => {
  assert.equal(wrapIndex(12, 0), 0);
});

test("reduced motion prevents autoplay but preserves manual carousel controls", async () => {
  const cleanup = installDom(`
    <section id="carousel">
      <div data-slide></div><div data-slide></div>
      <button data-dot></button><button data-dot></button>
      <button data-previous></button><button data-next></button>
    </section>
  `);
  const root = document.querySelector("#carousel");
  const slides = Array.from(root.querySelectorAll("[data-slide]"));
  const dots = Array.from(root.querySelectorAll("[data-dot]"));
  const carousel = createCarousel({
    root,
    slides,
    dots,
    previous: root.querySelector("[data-previous]"),
    next: root.querySelector("[data-next]"),
    interval: 5,
  });

  root.querySelector("[data-next]").click();
  assert.equal(carousel.getCurrent(), 1);
  assert.equal(slides[0].getAttribute("aria-hidden"), "true");
  assert.equal(slides[0].hasAttribute("inert"), true);
  assert.equal(slides[1].getAttribute("aria-hidden"), "false");
  assert.equal(slides[1].hasAttribute("inert"), false);
  assert.equal(dots[1].getAttribute("aria-current"), "true");

  await new Promise((resolve) => {
    setTimeout(resolve, 20);
  });
  assert.equal(carousel.getCurrent(), 1);
  cleanup();
});

test("persistent pause survives restart attempts and exposes its state", async () => {
  const cleanup = installDom(
    `
      <section id="carousel">
        <div data-slide></div><div data-slide></div>
        <button data-toggle><span data-carousel-toggle-label></span></button>
      </section>
    `,
    { reducedMotion: false },
  );
  const root = document.querySelector("#carousel");
  const toggle = root.querySelector("[data-toggle]");
  const carousel = createCarousel({
    root,
    slides: Array.from(root.querySelectorAll("[data-slide]")),
    toggle,
    interval: 5,
  });

  toggle.click();
  const pausedAt = carousel.getCurrent();
  carousel.start();
  await new Promise((resolve) => {
    setTimeout(resolve, 20);
  });

  assert.equal(carousel.getCurrent(), pausedAt);
  assert.equal(carousel.isUserPaused(), true);
  assert.equal(toggle.getAttribute("aria-pressed"), "true");
  assert.equal(toggle.textContent, "ادامه نمایش خودکار");

  toggle.click();
  assert.equal(carousel.isUserPaused(), false);
  assert.equal(toggle.getAttribute("aria-pressed"), "false");
  carousel.stop();
  cleanup();
});

test("logical rail movement respects RTL direction", () => {
  assert.equal(logicalScrollDelta(1, false, 240), 240);
  assert.equal(logicalScrollDelta(-1, false, 240), -240);
  assert.equal(logicalScrollDelta(1, true, 240), -240);
  assert.equal(logicalScrollDelta(-1, true, 240), 240);
});
