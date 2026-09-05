document.addEventListener("DOMContentLoaded", function () {
  const root = document.documentElement;
  const sections = Array.from(document.querySelectorAll(".page-home [data-reveal]"));
  if (!sections.length) return;

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced || !("IntersectionObserver" in window)) {
    sections.forEach((section) => section.classList.add("is-revealed"));
    return;
  }

  root.classList.add("js-home-motion");

  sections.forEach((section) => {
    section.querySelectorAll("[data-reveal-group]").forEach((group) => {
      Array.from(group.children).forEach((item, index) => {
        item.style.setProperty("--reveal-delay", `${Math.min(index, 5) * 55}ms`);
      });
    });
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-revealed");
      observer.unobserve(entry.target);
    });
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });

  sections.forEach((section) => observer.observe(section));
});
