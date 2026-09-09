(() => {
  "use strict";
  const films = document.querySelectorAll("[data-wedding-film]");
  const pause = () => films.forEach((video) => video.pause());
  document.addEventListener("visibilitychange", () => { if (document.hidden) pause(); });
  window.addEventListener("pagehide", pause);
})();
