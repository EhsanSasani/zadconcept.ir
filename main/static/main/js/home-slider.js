document.addEventListener("DOMContentLoaded", function () {
  const slides = Array.from(document.querySelectorAll(".hero-slide"));
  const dots = Array.from(document.querySelectorAll(".hero-slider__dots button"));
  const prev = document.getElementById("heroPrev");
  const next = document.getElementById("heroNext");

  if (!slides.length) return;

  let current = 0;
  let timer = null;
  let touchStartX = 0;
  let touchStartY = 0;
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function showSlide(index) {
    slides.forEach((slide, i) => {
      const active = i === index;
      slide.classList.toggle("is-active", active);
      slide.setAttribute("aria-hidden", active ? "false" : "true");
    });
    dots.forEach((dot, i) => {
      const active = i === index;
      dot.classList.toggle("is-active", active);
      dot.setAttribute("aria-current", active ? "true" : "false");
    });
    current = index;
  }

  function nextSlide() {
    showSlide((current + 1) % slides.length);
  }

  function prevSlide() {
    showSlide((current - 1 + slides.length) % slides.length);
  }

  function startAuto() {
    stopAuto();
    if (prefersReducedMotion.matches) return;
    timer = setInterval(nextSlide, 5000);
  }

  function stopAuto() {
    if (timer) clearInterval(timer);
  }

  if (next) {
    next.addEventListener("click", function () {
      nextSlide();
      startAuto();
    });
  }

  if (prev) {
    prev.addEventListener("click", function () {
      prevSlide();
      startAuto();
    });
  }

  dots.forEach((dot, index) => {
    dot.addEventListener("click", function () {
      showSlide(index);
      startAuto();
    });
  });

  const hero = document.querySelector(".home-hero");
  hero?.addEventListener("mouseenter", stopAuto);
  hero?.addEventListener("mouseleave", startAuto);
  hero?.addEventListener("focusin", stopAuto);
  hero?.addEventListener("focusout", startAuto);

  hero?.addEventListener("touchstart", function (event) {
    const touch = event.changedTouches[0];
    touchStartX = touch.clientX;
    touchStartY = touch.clientY;
    stopAuto();
  }, { passive: true });

  hero?.addEventListener("touchend", function (event) {
    const touch = event.changedTouches[0];
    const deltaX = touch.clientX - touchStartX;
    const deltaY = touch.clientY - touchStartY;

    if (Math.abs(deltaX) > 48 && Math.abs(deltaX) > Math.abs(deltaY) * 1.2) {
      if (deltaX < 0) nextSlide();
      else prevSlide();
    }
    startAuto();
  }, { passive: true });

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) stopAuto();
    else startAuto();
  });

  prefersReducedMotion.addEventListener?.("change", function () {
    if (prefersReducedMotion.matches) stopAuto();
    else startAuto();
  });

  showSlide(0);
  // startAuto();
});
