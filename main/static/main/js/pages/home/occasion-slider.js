document.addEventListener("DOMContentLoaded", () => {
  const slider = document.querySelector(".home-occasions-row");

  if (!slider) return;

  const isMobile = () => window.matchMedia("(max-width: 760px)").matches;
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  let index = 0;
  let timer = null;

  const getCards = () => Array.from(slider.querySelectorAll(".home-occasion-card"));

  const goNext = () => {
    if (!isMobile()) return;

    const cards = getCards();
    if (!cards.length) return;

    index = (index + 1) % cards.length;

    slider.scrollTo({
      left: cards[index].offsetLeft - slider.offsetLeft,
      behavior: "smooth",
    });
  };

  const start = () => {
    stop();
    if (prefersReducedMotion.matches || document.hidden) return;
    timer = setInterval(goNext, 3200);
  };

  const stop = () => {
    if (timer) clearInterval(timer);
    timer = null;
  };

  slider.addEventListener("mouseenter", stop);
  slider.addEventListener("mouseleave", start);
  slider.addEventListener("touchstart", stop, { passive: true });
  slider.addEventListener("touchend", start, { passive: true });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
    else start();
  });
  prefersReducedMotion.addEventListener?.("change", start);

  start();

  window.addEventListener("resize", () => {
    index = 0;
    slider.scrollTo({ left: 0, behavior: "smooth" });
    start();
  });
});
