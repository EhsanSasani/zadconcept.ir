import { preferredScrollBehavior } from "../core/motion.js";
import { logicalScrollDelta } from "../core/direction.js";

export function initProductRail(slider) {
  const viewport = slider.querySelector("[data-featured-viewport]");
  const track = slider.querySelector("[data-featured-track]");
  const cards = Array.from(track?.querySelectorAll("[data-featured-card]") || []);
  const previous = slider.querySelector("[data-featured-prev]");
  const next = slider.querySelector("[data-featured-next]");
  if (!viewport || !track || cards.length === 0) return;

  const getStep = () => {
    const style = window.getComputedStyle(track);
    const gap = Number.parseFloat(style.gap || style.columnGap || "0") || 0;
    return cards[0].getBoundingClientRect().width + gap;
  };

  const move = (direction) => {
    const isRtl = window.getComputedStyle(viewport).direction === "rtl";
    viewport.scrollBy({
      left: logicalScrollDelta(direction, isRtl, getStep()),
      behavior: preferredScrollBehavior(),
    });
  };

  const syncControls = () => {
    const hasOverflow = viewport.scrollWidth > viewport.clientWidth + 1;
    [previous, next].forEach((control) => {
      if (!control) return;
      control.hidden = !hasOverflow;
      control.disabled = !hasOverflow;
    });
  };

  previous?.addEventListener("click", () => move(-1));
  next?.addEventListener("click", () => move(1));

  if ("ResizeObserver" in window) {
    const observer = new ResizeObserver(syncControls);
    observer.observe(viewport);
    observer.observe(track);
  } else {
    window.addEventListener("resize", syncControls);
  }

  syncControls();
}

export function initProductRails() {
  document.querySelectorAll("[data-featured-slider]").forEach(initProductRail);
}

initProductRails();
