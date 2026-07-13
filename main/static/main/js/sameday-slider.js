document.addEventListener("DOMContentLoaded", function () {
  const slider = document.querySelector("[data-sameday-slider]");
  if (!slider) return;

  const originalCards = Array.from(
    slider.querySelectorAll(".home-sameday-card")
  );

  if (originalCards.length < 2) return;

  originalCards.forEach(function (card) {
    slider.appendChild(card.cloneNode(true));
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

  start();
});