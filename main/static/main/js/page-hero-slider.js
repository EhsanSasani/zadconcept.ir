document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-page-hero-slider]").forEach((root) => {
    const slides = Array.from(root.querySelectorAll("[data-page-hero-slide]"));
    const dots = Array.from(root.querySelectorAll("[data-page-hero-dot]"));
    const previous = root.querySelector("[data-page-hero-prev]");
    const next = root.querySelector("[data-page-hero-next]");
    const title = root.querySelector("[data-page-hero-title]");
    const kicker = root.querySelector("[data-page-hero-kicker]");
    const text = root.querySelector("[data-page-hero-text]");

    if (slides.length < 2) return;

    let current = 0;
    let timer = null;
    let touchStartX = 0;
    let touchStartY = 0;

    function replacePrefixedClass(prefix, nextClass) {
      Array.from(root.classList).forEach((className) => {
        if (className.indexOf(prefix) === 0) root.classList.remove(className);
      });
      if (nextClass) root.classList.add(nextClass);
    }

    function show(index) {
      current = (index + slides.length) % slides.length;
      slides.forEach((slide, itemIndex) => {
        slide.classList.toggle("is-active", itemIndex === current);
        slide.setAttribute("aria-hidden", itemIndex === current ? "false" : "true");
      });
      dots.forEach((dot, itemIndex) => {
        dot.classList.toggle("is-active", itemIndex === current);
        dot.setAttribute("aria-current", itemIndex === current ? "true" : "false");
      });
      const activeSlide = slides[current];
      if (title && activeSlide.dataset.heroTitle) title.textContent = activeSlide.dataset.heroTitle;
      if (kicker) kicker.textContent = activeSlide.dataset.heroKicker || "";
      if (text) text.textContent = activeSlide.dataset.heroText || "";
      replacePrefixedClass("hero-style-", activeSlide.dataset.heroStyleClass || "");
      replacePrefixedClass(
        "hero-position--",
        `hero-position--${activeSlide.dataset.heroPosition || "center-left"}`
      );
      replacePrefixedClass(
        "hero-mobile-position--",
        `hero-mobile-position--${activeSlide.dataset.heroMobilePosition || "bottom-center"}`
      );
    }

    function stop() {
      if (timer) window.clearInterval(timer);
      timer = null;
    }

    function start() {
      stop();
      timer = window.setInterval(() => show(current + 1), 6000);
    }

    previous?.addEventListener("click", () => {
      show(current - 1);
      start();
    });
    next?.addEventListener("click", () => {
      show(current + 1);
      start();
    });
    dots.forEach((dot, index) => {
      dot.addEventListener("click", () => {
        show(index);
        start();
      });
    });

    root.addEventListener("touchstart", (event) => {
      const touch = event.changedTouches[0];
      touchStartX = touch.clientX;
      touchStartY = touch.clientY;
      stop();
    }, { passive: true });

    root.addEventListener("touchend", (event) => {
      const touch = event.changedTouches[0];
      const deltaX = touch.clientX - touchStartX;
      const deltaY = touch.clientY - touchStartY;

      if (Math.abs(deltaX) > 48 && Math.abs(deltaX) > Math.abs(deltaY) * 1.2) {
        show(current + (deltaX < 0 ? 1 : -1));
      }
      start();
    }, { passive: true });

    root.addEventListener("mouseenter", stop);
    root.addEventListener("mouseleave", start);
    root.addEventListener("focusin", stop);
    root.addEventListener("focusout", start);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stop();
      else start();
    });

    show(0);
    start();
  });
});
