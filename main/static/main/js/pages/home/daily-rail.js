/* Native swipe/keyboard scrolling; the small line reflects actual overflow. */
(() => {
  document.querySelectorAll('[data-daily-rail]').forEach((rail) => {
    const progress = rail.parentElement.querySelector('[data-daily-progress]');
    if (!progress) return;
    const thumb = progress.firstElementChild;
    let frame = 0;

    function update() {
      frame = 0;
      const overflow = rail.scrollWidth - rail.clientWidth;
      progress.hidden = overflow <= 1;
      if (progress.hidden) return;
      const fraction = Math.min(1, Math.max(0, rail.scrollLeft / overflow));
      const width = Math.max(12, 48 * rail.clientWidth / rail.scrollWidth);
      thumb.style.width = `${width}px`;
      thumb.style.transform = `translateX(${fraction * (48 - width)}px)`;
    }

    function schedule() {
      if (!frame) frame = requestAnimationFrame(update);
    }

    rail.addEventListener('scroll', schedule, { passive: true });
    // Focus stays on the rail. Links retain their native keyboard behavior.
    rail.addEventListener('keydown', (event) => {
      if (event.target !== rail || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const card = rail.firstElementChild;
      const step = card ? card.getBoundingClientRect().width + parseFloat(getComputedStyle(rail).gap || '0') : rail.clientWidth;
      let left;
      if (event.key === 'ArrowRight') left = rail.scrollLeft + step;
      else if (event.key === 'ArrowLeft') left = rail.scrollLeft - step;
      else if (event.key === 'Home') left = 0;
      else if (event.key === 'End') left = rail.scrollWidth;
      else return;
      event.preventDefault();
      rail.scrollTo({ left, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    });
    if ('ResizeObserver' in window) {
      const observer = new ResizeObserver(schedule);
      observer.observe(rail);
    } else {
      window.addEventListener('resize', schedule, { passive: true });
    }
    update();
  });
})();
