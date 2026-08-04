function initDropdown(dropdown) {
  const trigger = dropdown.querySelector("[data-nav-dropdown-trigger]");
  const menu = dropdown.querySelector("[data-nav-dropdown-menu]");
  if (!trigger || !menu) return;

  const isNativeDisclosure = dropdown.tagName === "DETAILS";

  function isOpen() {
    return isNativeDisclosure ? dropdown.open : dropdown.classList.contains("is-open");
  }

  function setOpen(isOpen, { restoreFocus = false } = {}) {
    if (isNativeDisclosure) dropdown.open = isOpen;
    dropdown.classList.toggle("is-open", isOpen);
    trigger.setAttribute("aria-expanded", String(isOpen));
    if (!isOpen && restoreFocus) trigger.focus();
  }

  trigger.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    setOpen(!isOpen());
  });

  dropdown.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !isOpen()) return;
    event.preventDefault();
    setOpen(false, { restoreFocus: true });
  });

  dropdown.addEventListener("focusout", (event) => {
    if (!dropdown.contains(event.relatedTarget)) setOpen(false);
  });

  document.addEventListener("click", (event) => {
    if (!dropdown.contains(event.target)) setOpen(false);
  });
  window.addEventListener("resize", () => setOpen(false));

  setOpen(isNativeDisclosure && dropdown.open);
}

function initStickyHeader() {
  const header = document.querySelector("[data-site-header]");
  if (!header) return;

  let scheduled = false;
  const update = () => {
    header.classList.toggle("is-scrolled", window.scrollY > 80);
    scheduled = false;
  };

  window.addEventListener(
    "scroll",
    () => {
      if (scheduled) return;
      scheduled = true;
      window.requestAnimationFrame(update);
    },
    { passive: true },
  );
  update();
}

export function initNavigation() {
  document.querySelectorAll("[data-nav-dropdown]").forEach(initDropdown);
  initStickyHeader();
}
