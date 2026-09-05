document.addEventListener("DOMContentLoaded", function () {
  const slider = document.querySelector("[data-sameday-slider]");
  if (!slider) return;

  const originalCards = Array.from(
    slider.querySelectorAll(".home-sameday-card")
  );

  if (originalCards.length < 2) return;

  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  originalCards.forEach(function (card) {
    const clone = card.cloneNode(true);
    clone.setAttribute("aria-hidden", "true");
    clone.querySelectorAll("a, button, input, select, textarea").forEach(function (item) {
      item.tabIndex = -1;
    });
    slider.appendChild(clone);
  });

  let timer = null;
  let resetTimer = null;

  function getStep() {
    const firstCard = slider.querySelector(".home-sameday-card");
    if (!firstCard) return 0;

    const styles = window.getComputedStyle(slider);
    const gap = parseFloat(styles.columnGap || styles.gap || 0);

    return firstCard.offsetWidth + gap;
  }

  function moveNext() {
    const step = getStep();
    if (!step) return;

    const direction = window.getComputedStyle(slider).direction;
    slider.scrollBy({
      left: direction === "rtl" ? -step : step,
      behavior: "smooth",
    });
  }

  function normalizePosition() {
    const step = getStep();
    if (!step) return;

    const originalWidth = step * originalCards.length;
    const direction = window.getComputedStyle(slider).direction;
    const travelled = direction === "rtl" ? -slider.scrollLeft : slider.scrollLeft;

    if (travelled < originalWidth - 2) return;

    slider.style.scrollBehavior = "auto";
    slider.scrollLeft += direction === "rtl" ? originalWidth : -originalWidth;
    slider.offsetHeight;
    slider.style.scrollBehavior = "";
  }

  function start() {
    stop();
    if (prefersReducedMotion.matches || document.hidden) return;
    timer = window.setInterval(moveNext, 2800);
  }

  function stop() {
    if (timer) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  slider.addEventListener("mouseenter", stop);
  slider.addEventListener("mouseleave", start);
  slider.addEventListener("touchstart", stop, { passive: true });
  slider.addEventListener("touchend", start, { passive: true });
  slider.addEventListener(
    "scroll",
    function () {
      window.clearTimeout(resetTimer);
      resetTimer = window.setTimeout(normalizePosition, 120);
    },
    { passive: true }
  );

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) stop();
    else start();
  });
  prefersReducedMotion.addEventListener?.("change", start);

  start();
});
