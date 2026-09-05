document.addEventListener("DOMContentLoaded", function () {
  const header = document.querySelector("[data-site-header]");
  const menu = document.querySelector("[data-site-menu]");
  const openButtons = Array.from(document.querySelectorAll("[data-site-menu-open]"));
  const search = document.querySelector("[data-site-search]");
  const searchOpen = document.querySelector("[data-site-search-open]");
  const searchClose = document.querySelector("[data-site-search-close]");
  const searchInput = document.querySelector("[data-site-search-input]");
  const searchLinks = Array.from(document.querySelectorAll("[data-site-search-list] a"));
  const searchEmpty = document.querySelector("[data-site-search-empty]");

  let lastFocused = null;
  let menuCloseTimer = null;
  let searchCloseTimer = null;

  const menuPanel = menu?.querySelector(".zad-site-menu__panel");
  const menuCloseButtons = menu ? Array.from(menu.querySelectorAll("[data-site-menu-close]")) : [];

  const focusables = (root) => Array.from(root?.querySelectorAll(
    'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
  ) || []).filter((node) => !node.hidden && node.offsetParent !== null);

  function setMenuExpanded(value) {
    openButtons.forEach((button) => button.setAttribute("aria-expanded", value ? "true" : "false"));
  }

  function openMenu() {
    if (!menu || menu.classList.contains("is-open")) return;
    closeSearch({ restoreFocus: false, immediate: true });
    if (menuCloseTimer) window.clearTimeout(menuCloseTimer);
    lastFocused = document.activeElement;
    menu.hidden = false;
    menu.setAttribute("aria-hidden", "false");
    document.documentElement.classList.add("has-zad-menu");
    document.body.classList.add("has-zad-menu");
    setMenuExpanded(true);
    window.requestAnimationFrame(() => {
      menu.classList.add("is-open");
      window.setTimeout(() => menuPanel?.focus({ preventScroll: true }), 80);
    });
  }

  function closeMenu({ restoreFocus = true, immediate = false } = {}) {
    if (!menu || menu.hidden) return;
    menu.classList.remove("is-open");
    menu.setAttribute("aria-hidden", "true");
    document.documentElement.classList.remove("has-zad-menu");
    document.body.classList.remove("has-zad-menu");
    setMenuExpanded(false);

    const finish = () => {
      menu.hidden = true;
      menuCloseTimer = null;
      if (restoreFocus && lastFocused && typeof lastFocused.focus === "function") {
        lastFocused.focus({ preventScroll: true });
      }
      lastFocused = null;
    };

    if (immediate) finish();
    else menuCloseTimer = window.setTimeout(finish, 360);
  }

  function openSearch() {
    if (!search || search.classList.contains("is-open")) return;
    closeMenu({ restoreFocus: false, immediate: true });
    if (searchCloseTimer) window.clearTimeout(searchCloseTimer);
    lastFocused = document.activeElement;
    search.hidden = false;
    search.setAttribute("aria-hidden", "false");
    searchOpen?.setAttribute("aria-expanded", "true");
    window.requestAnimationFrame(() => {
      search.classList.add("is-open");
      window.setTimeout(() => searchInput?.focus({ preventScroll: true }), 90);
    });
  }

  function closeSearch({ restoreFocus = true, immediate = false } = {}) {
    if (!search || search.hidden) return;
    search.classList.remove("is-open");
    search.setAttribute("aria-hidden", "true");
    searchOpen?.setAttribute("aria-expanded", "false");

    const finish = () => {
      search.hidden = true;
      searchCloseTimer = null;
      if (restoreFocus && lastFocused && typeof lastFocused.focus === "function") {
        lastFocused.focus({ preventScroll: true });
      }
      lastFocused = null;
    };

    if (immediate) finish();
    else searchCloseTimer = window.setTimeout(finish, 260);
  }

  openButtons.forEach((button) => button.addEventListener("click", () => {
    if (menu?.classList.contains("is-open")) closeMenu();
    else openMenu();
  }));

  menuCloseButtons.forEach((button) => button.addEventListener("click", () => closeMenu()));

  menu?.addEventListener("click", (event) => {
    if (event.target.closest("a[href]")) closeMenu({ restoreFocus: false });
  });

  searchOpen?.addEventListener("click", () => {
    if (search?.classList.contains("is-open")) closeSearch();
    else openSearch();
  });
  searchClose?.addEventListener("click", () => closeSearch());

  search?.addEventListener("click", (event) => {
    if (event.target === search) closeSearch();
    if (event.target.closest("a[href]")) closeSearch({ restoreFocus: false });
  });

  searchInput?.addEventListener("input", () => {
    const query = (searchInput.value || "").trim().toLocaleLowerCase("fa");
    let visible = 0;
    searchLinks.forEach((link) => {
      const haystack = (link.dataset.searchText || link.textContent || "").toLocaleLowerCase("fa");
      const match = !query || haystack.includes(query);
      link.hidden = !match;
      if (match) visible += 1;
    });
    if (searchEmpty) searchEmpty.hidden = visible > 0;
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (search && !search.hidden) {
        event.preventDefault();
        closeSearch();
        return;
      }
      if (menu && !menu.hidden) {
        event.preventDefault();
        closeMenu();
      }
      return;
    }

    if (event.key !== "Tab") return;
    const activeRoot = menu && !menu.hidden ? menuPanel : (search && !search.hidden ? search.querySelector(".zad-quick-search__panel") : null);
    if (!activeRoot) return;
    const items = focusables(activeRoot);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  function updateHeader() {
    header?.classList.toggle("is-scrolled", window.scrollY > 18);
  }

  updateHeader();
  window.addEventListener("scroll", updateHeader, { passive: true });
});
