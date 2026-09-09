document.addEventListener("DOMContentLoaded", function () {
  "use strict";
  const overlays = window.ZadOverlays;
  if (!overlays) return;
  const header = document.querySelector("[data-site-header]");
  const menu = document.querySelector("[data-site-menu]");
  const search = document.querySelector("[data-site-search]");
  const openButtons = Array.from(document.querySelectorAll("[data-site-menu-open]"));
  const searchOpen = document.querySelector("[data-site-search-open]");
  const searchInput = document.querySelector("[data-site-search-input]");
  const searchLinks = Array.from(document.querySelectorAll("[data-site-search-list] a"));
  const searchEmpty = document.querySelector("[data-site-search-empty]");
  const surfaces = new Map();
  if (menu) surfaces.set(menu, { controls: openButtons, focus: menu.querySelector(".zad-site-menu__close") });
  if (search) surfaces.set(search, { controls: [searchOpen].filter(Boolean), focus: searchInput });

  function close(root, { restoreFocus = true, immediate = false } = {}) {
    const state = surfaces.get(root);
    if (!state || root.hidden) return;
    if (state.closing && !immediate) return;
    state.closing = true;
    window.clearTimeout(state.timer);
    root.classList.remove("is-open");
    state.controls.forEach((button) => button.setAttribute("aria-expanded", "false"));
    const finish = () => {
      overlays.close(root, { restoreFocus });
      root.hidden = true;
      root.setAttribute("aria-hidden", "true");
      state.closing = false;
      state.timer = null;
    };
    if (immediate || overlays.reducedMotion()) finish();
    else state.timer = window.setTimeout(finish, 260);
  }

  function open(root) {
    const state = surfaces.get(root);
    if (!state) return;
    if (!root.hidden && !state.closing) return;
    surfaces.forEach((_, other) => {
      if (other !== root) close(other, { restoreFocus: false, immediate: true });
    });
    if (state.closing) close(root, { restoreFocus: false, immediate: true });
    root.style.setProperty("--zad-panel-top", `${Math.max(12, (header?.getBoundingClientRect().bottom || 0) + 8)}px`);
    root.hidden = false;
    root.setAttribute("aria-hidden", "false");
    // Establish the closed style once so the entrance transition can run.
    void root.offsetWidth;
    root.classList.add("is-open");
    state.controls.forEach((button) => button.setAttribute("aria-expanded", "true"));
    overlays.open(root, { focus: state.focus, onClose: () => close(root) });
  }

  openButtons.forEach((button) => button.addEventListener("click", () => open(menu)));
  menu?.querySelectorAll("[data-site-menu-close]").forEach((button) =>
    button.addEventListener("click", () => close(menu))
  );
  searchOpen?.addEventListener("click", () => open(search));
  search?.querySelector("[data-site-search-close]")?.addEventListener("click", () => close(search));
  surfaces.forEach((_, root) => root.addEventListener("click", (event) => {
    if (root === search && event.target === search) close(search);
    if (event.target.closest("a[href]")) close(root, { restoreFocus: false, immediate: true });
  }));

  const normalize = (value) => value.normalize("NFKC").toLocaleLowerCase("fa")
    .replace(/[يى]/g, "ی").replace(/ك/g, "ک").replace(/[\u200c\u200d]/g, " ")
    .replace(/\s+/g, " ").trim();
  searchInput?.addEventListener("input", () => {
    const query = normalize(searchInput.value || "");
    let visible = 0;
    searchLinks.forEach((link) => {
      const match = normalize(link.dataset.searchText || link.textContent || "").includes(query);
      link.hidden = !match;
      if (match) visible += 1;
    });
    if (searchEmpty) searchEmpty.hidden = visible > 0;
  });

  function updateHeader() {
    header?.classList.toggle("is-scrolled", window.scrollY > 18);
  }
  updateHeader();
  window.addEventListener("scroll", updateHeader, { passive: true });
});
