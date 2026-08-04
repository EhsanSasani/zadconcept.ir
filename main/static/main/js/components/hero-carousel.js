import { createCarousel } from "../core/carousel.js";

function replacePrefixedClass(root, prefix, nextClass) {
  Array.from(root.classList).forEach((className) => {
    if (className.startsWith(prefix)) root.classList.remove(className);
  });
  if (nextClass) root.classList.add(nextClass);
}

function initHomeHero(root) {
  const slides = Array.from(root.querySelectorAll("[data-home-hero-slide]"));
  const dots = Array.from(root.querySelectorAll("[data-home-hero-dot]"));

  createCarousel({
    root,
    slides,
    dots,
    previous: root.querySelector("[data-home-hero-prev]"),
    next: root.querySelector("[data-home-hero-next]"),
    interval: 5000,
  });
}

function initPageHero(root) {
  const slides = Array.from(root.querySelectorAll("[data-page-hero-slide]"));
  if (slides.length < 2) return;

  const title = root.querySelector("[data-page-hero-title]");
  const kicker = root.querySelector("[data-page-hero-kicker]");
  const text = root.querySelector("[data-page-hero-text]");

  createCarousel({
    root,
    slides,
    dots: Array.from(root.querySelectorAll("[data-page-hero-dot]")),
    previous: root.querySelector("[data-page-hero-prev]"),
    next: root.querySelector("[data-page-hero-next]"),
    interval: 6000,
    onChange(activeSlide) {
      if (title && activeSlide.dataset.heroTitle) title.textContent = activeSlide.dataset.heroTitle;
      if (kicker) kicker.textContent = activeSlide.dataset.heroKicker || "";
      if (text) text.textContent = activeSlide.dataset.heroText || "";
      replacePrefixedClass(root, "hero-style-", activeSlide.dataset.heroStyleClass || "");
      replacePrefixedClass(
        root,
        "hero-position--",
        `hero-position--${activeSlide.dataset.heroPosition || "center-left"}`,
      );
      replacePrefixedClass(
        root,
        "hero-mobile-position--",
        `hero-mobile-position--${activeSlide.dataset.heroMobilePosition || "bottom-center"}`,
      );
    },
  });
}

export function initHeroCarousels() {
  document.querySelectorAll("[data-home-hero]").forEach(initHomeHero);
  document.querySelectorAll("[data-page-hero-slider]").forEach(initPageHero);
}
