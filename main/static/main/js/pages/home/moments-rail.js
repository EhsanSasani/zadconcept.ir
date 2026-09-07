/* Native touch/trackpad scrolling, plus keyboard access. No rail arrow buttons.
   The existing story viewer still owns clip/cube navigation. */
(() => {
  "use strict";

  function setupRail(rail) {
    const track = rail.querySelector("[data-moments-track]");
    if (!track) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    track.addEventListener("keydown", (event) => {
      // Tab/Enter/Space keep their native behavior; arrow keys follow the LTR rail.
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
      if (!step) return;
      const triggers = Array.from(track.querySelectorAll("[data-story-trigger]"));
      const index = triggers.indexOf(document.activeElement);
      const target = triggers[index + step];
      if (index < 0 || !target) return;
      event.preventDefault();
      target.focus({ preventScroll: true });
      target.scrollIntoView({ block: "nearest", inline: "nearest", behavior: reduced.matches ? "instant" : "smooth" });
    });
  }

  function init() { document.querySelectorAll("[data-moments-rail]").forEach(setupRail); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
