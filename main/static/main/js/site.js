import { initNavigation } from "./components/navigation.js";

initNavigation();

const heroRoots = Array.from(
  document.querySelectorAll("[data-home-hero], [data-page-hero-slider]"),
);
const hasRotatingHero = heroRoots.some((root) => {
  return root.querySelectorAll("[data-home-hero-slide], [data-page-hero-slide]").length > 1;
});

if (hasRotatingHero) {
  import("./components/hero-carousel.js").then(({ initHeroCarousels }) => {
    initHeroCarousels();
  });
}

if (document.querySelector("[data-lead-form]")) {
  import("./components/lead-form.js").then(({ initLeadForms }) => {
    initLeadForms();
  });
}
