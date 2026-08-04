import { observeMotionPreference, prefersReducedMotion } from "./motion.js";
import { observeHorizontalSwipe } from "./swipe.js";

export function wrapIndex(index, length) {
  if (length <= 0) return 0;
  return ((index % length) + length) % length;
}

export function createCarousel({
  root,
  slides,
  dots = [],
  previous = null,
  next = null,
  interval = 0,
  onChange = () => {},
}) {
  if (!root || slides.length === 0) return null;

  let current = 0;
  let timer = null;

  function stop() {
    if (timer !== null) window.clearInterval(timer);
    timer = null;
  }

  function canRotate() {
    return interval > 0 && slides.length > 1 && !document.hidden && !prefersReducedMotion();
  }

  function start() {
    stop();
    if (!canRotate()) return;
    timer = window.setInterval(() => show(current + 1), interval);
  }

  function show(index, { restart = false } = {}) {
    current = wrapIndex(index, slides.length);

    slides.forEach((slide, itemIndex) => {
      const isActive = itemIndex === current;
      slide.classList.toggle("is-active", isActive);
      slide.setAttribute("aria-hidden", isActive ? "false" : "true");
    });

    dots.forEach((dot, itemIndex) => {
      const isActive = itemIndex === current;
      dot.classList.toggle("is-active", isActive);
      dot.setAttribute("aria-current", isActive ? "true" : "false");
    });

    onChange(slides[current], current);
    if (restart) start();
  }

  previous?.addEventListener("click", () => show(current - 1, { restart: true }));
  next?.addEventListener("click", () => show(current + 1, { restart: true }));
  dots.forEach((dot, index) => {
    dot.addEventListener("click", () => show(index, { restart: true }));
  });

  observeHorizontalSwipe(root, (direction) => show(current + direction, { restart: true }));
  observeMotionPreference(start);

  root.addEventListener("mouseenter", stop);
  root.addEventListener("mouseleave", start);
  root.addEventListener("focusin", stop);
  root.addEventListener("focusout", (event) => {
    if (!root.contains(event.relatedTarget)) start();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
    else start();
  });

  show(0);
  start();

  return { show, start, stop, getCurrent: () => current };
}
