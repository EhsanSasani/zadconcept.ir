document.addEventListener("DOMContentLoaded", function () {
  const hero = document.querySelector(".home-hero");
  if (!hero) return;

  const slides = Array.from(hero.querySelectorAll(".hero-slide"));
  const dots = Array.from(hero.querySelectorAll(".hero-slider__dots button"));
  const prev = document.getElementById("heroPrev");
  const next = document.getElementById("heroNext");
  if (!slides.length) return;

  let current = 0;
  let touchStartX = 0;
  let touchStartY = 0;

  function showSlide(index) {
    current = (index + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      const active = i === current;
      slide.classList.toggle("is-active", active);
      slide.setAttribute("aria-hidden", active ? "false" : "true");
    });
    dots.forEach((dot, i) => {
      const active = i === current;
      dot.classList.toggle("is-active", active);
      dot.setAttribute("aria-current", active ? "true" : "false");
    });
  }

  next?.addEventListener("click", () => showSlide(current + 1));
  prev?.addEventListener("click", () => showSlide(current - 1));
  dots.forEach((dot, index) => dot.addEventListener("click", () => showSlide(index)));

  hero.addEventListener("touchstart", (event) => {
    const touch = event.changedTouches[0];
    touchStartX = touch.clientX;
    touchStartY = touch.clientY;
  }, { passive: true });

  hero.addEventListener("touchend", (event) => {
    if (slides.length < 2) return;
    const touch = event.changedTouches[0];
    const dx = touch.clientX - touchStartX;
    const dy = touch.clientY - touchStartY;
    if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.25) {
      showSlide(current + (dx < 0 ? 1 : -1));
    }
  }, { passive: true });

  showSlide(0);
});
