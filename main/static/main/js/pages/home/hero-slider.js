document.addEventListener("DOMContentLoaded", function () {
  const hero = document.querySelector(".home-hero");
  if (!hero) return;

  const slides = Array.from(hero.querySelectorAll(".hero-slide"));
  const dots = Array.from(hero.querySelectorAll(".hero-slider__dots button"));
  const prev = document.getElementById("heroPrev");
  const next = document.getElementById("heroNext");
  if (!slides.length) return;

  const mobileViewport = window.matchMedia("(max-width: 760px)");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const defaultSlideDuration = 6000;

  let current = 0;
  let currentFrame = 0;
  let playbackTimer = null;
  let heroIsVisible = true;
  let touchStartX = 0;
  let touchStartY = 0;

  function clearPlaybackTimer() {
    if (playbackTimer === null) return;
    window.clearTimeout(playbackTimer);
    playbackTimer = null;
  }

  function getSequence(slide) {
    return slide?.querySelector("[data-hero-frame-sequence]") || null;
  }

  function getFrames(slide) {
    const sequence = getSequence(slide);
    return sequence ? Array.from(sequence.querySelectorAll("[data-hero-frame]")) : [];
  }

  function showFrame(slide, index) {
    const frames = getFrames(slide);
    if (!frames.length) {
      currentFrame = 0;
      return;
    }

    currentFrame = Math.min(Math.max(index, 0), frames.length - 1);
    frames.forEach((frame, frameIndex) => {
      frame.classList.toggle("is-active", frameIndex === currentFrame);
    });
  }

  function resetFrames() {
    slides.forEach((slide) => showFrame(slide, 0));
    currentFrame = 0;
  }

  function canAutoPlay() {
    return (
      !reducedMotion.matches &&
      !document.hidden &&
      heroIsVisible
    );
  }

  function schedulePlayback() {
    clearPlaybackTimer();
    if (!canAutoPlay()) return;

    const activeSlide = slides[current];
    const sequence = getSequence(activeSlide);
    const frames = getFrames(activeSlide);
    const frameDuration = Number(sequence?.dataset.frameDuration) || 2000;
    const duration = frames.length > 1 ? frameDuration : defaultSlideDuration;
    if (slides.length === 1 && frames.length <= 1) return;

    playbackTimer = window.setTimeout(() => {
      if (frames.length > 1 && currentFrame < frames.length - 1) {
        showFrame(activeSlide, currentFrame + 1);
        schedulePlayback();
        return;
      }

      showSlide(slides.length > 1 ? current + 1 : current);
    }, duration);
  }

  function showSlide(index) {
    clearPlaybackTimer();
    current = (index + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      const active = i === current;
      slide.classList.toggle("is-active", active);
      slide.setAttribute("aria-hidden", active ? "false" : "true");
      showFrame(slide, 0);
    });
    currentFrame = 0;
    dots.forEach((dot, i) => {
      const active = i === current;
      dot.classList.toggle("is-active", active);
      dot.setAttribute("aria-current", active ? "true" : "false");
    });
    schedulePlayback();
  }

  next?.addEventListener("click", () => showSlide(current + 1));
  prev?.addEventListener("click", () => showSlide(current - 1));
  dots.forEach((dot, index) => dot.addEventListener("click", () => showSlide(index)));

  hero.addEventListener("touchstart", (event) => {
    clearPlaybackTimer();
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
      return;
    }
    schedulePlayback();
  }, { passive: true });

  hero.addEventListener("touchcancel", schedulePlayback, { passive: true });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearPlaybackTimer();
    else schedulePlayback();
  });

  const handleMotionModeChange = () => {
    resetFrames();
    schedulePlayback();
  };
  mobileViewport.addEventListener?.("change", handleMotionModeChange);
  reducedMotion.addEventListener?.("change", handleMotionModeChange);

  if ("IntersectionObserver" in window) {
    const visibilityObserver = new IntersectionObserver((entries) => {
      heroIsVisible = Boolean(entries[0]?.isIntersecting);
      if (heroIsVisible) schedulePlayback();
      else clearPlaybackTimer();
    }, { threshold: 0.15 });
    visibilityObserver.observe(hero);
  }

  window.addEventListener("pagehide", clearPlaybackTimer, { once: true });
  showSlide(0);
});
