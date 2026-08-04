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
  toggle = null,
  interval = 0,
  onChange = () => {},
}) {
  if (!root || slides.length === 0) return null;

  let current = 0;
  let timer = null;
  let userPaused = false;

  function setToggleLabel(text) {
    if (!toggle) return;
    const label = toggle.querySelector("[data-carousel-toggle-label]");
    if (label) label.textContent = text;
    toggle.setAttribute("aria-label", text);
  }

  function syncToggle() {
    if (!toggle) return;
    const unavailable = interval <= 0 || slides.length <= 1;
    const motionDisabled = prefersReducedMotion();
    toggle.hidden = unavailable || motionDisabled;
    toggle.setAttribute("aria-pressed", String(userPaused));
    setToggleLabel(userPaused ? "ادامه نمایش خودکار" : "توقف نمایش خودکار");
  }

  function stop() {
    if (timer !== null) window.clearInterval(timer);
    timer = null;
  }

  function canRotate() {
    const hasPointerPause = root.matches?.(":hover") ?? false;
    const hasFocusPause = root.contains(document.activeElement);
    return (
      interval > 0 &&
      slides.length > 1 &&
      !userPaused &&
      !document.hidden &&
      !hasPointerPause &&
      !hasFocusPause &&
      !prefersReducedMotion()
    );
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
      if (isActive) slide.removeAttribute("inert");
      else slide.setAttribute("inert", "");
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

  toggle?.addEventListener("click", () => {
    userPaused = !userPaused;
    if (userPaused) stop();
    else start();
    syncToggle();
  });

  observeHorizontalSwipe(root, (direction) => show(current + direction, { restart: true }));
  observeMotionPreference(() => {
    syncToggle();
    start();
  });

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
  syncToggle();
  start();

  return {
    show,
    start,
    stop,
    getCurrent: () => current,
    isUserPaused: () => userPaused,
  };
}
