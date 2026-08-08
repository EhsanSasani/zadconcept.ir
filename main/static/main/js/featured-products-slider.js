document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-featured-slider]").forEach((slider) => {
    const viewport = slider.querySelector("[data-featured-viewport]");
    const track = slider.querySelector("[data-featured-track]");

    if (!viewport || !track) return;

    const cards = [...track.querySelectorAll(".featured-product-card")];

    if (cards.length === 0) return;

    const prevBtn = slider.querySelector("[data-featured-prev]");
    const nextBtn = slider.querySelector("[data-featured-next]");

    const getGap = () => {
      const style = getComputedStyle(track);
      return parseFloat(style.gap || style.columnGap || "0") || 0;
    };

    const getStep = () => {
      return cards[0].getBoundingClientRect().width + getGap();
    };

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    const move = (direction) => {
      viewport.scrollBy({
        left: direction * getStep(),
        behavior: prefersReducedMotion.matches ? "auto" : "smooth",
      });
    };

    if (prevBtn) {
      prevBtn.disabled = false;
      prevBtn.addEventListener("click", () => move(-1));
    }

    if (nextBtn) {
      nextBtn.disabled = false;
      nextBtn.addEventListener("click", () => move(1));
    }
  });
});
