document.addEventListener("DOMContentLoaded", function () {
  const dropdown = document.querySelector("[data-nav-dropdown]");
  const trigger = document.querySelector("[data-nav-dropdown-trigger]");
  const center = dropdown?.closest(".main-nav__center");

  if (!dropdown || !trigger) return;

  trigger.setAttribute("aria-expanded", "false");

  function setDropdownOpen(isOpen) {
    dropdown.classList.toggle("is-open", isOpen);
    center?.classList.toggle("has-open-dropdown", isOpen);
    trigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
  }

  trigger.addEventListener("click", function (event) {
    event.preventDefault();
    event.stopPropagation();
    setDropdownOpen(!dropdown.classList.contains("is-open"));
  });

  document.addEventListener("click", function (event) {
    if (!dropdown.contains(event.target)) {
      setDropdownOpen(false);
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && dropdown.classList.contains("is-open")) {
      setDropdownOpen(false);
      trigger.focus();
    }
  });

  window.addEventListener("resize", function () {
    setDropdownOpen(false);
  });
});

document.addEventListener("DOMContentLoaded", function () {

  const header = document.querySelector(".site-header");

  if (!header) return;

  function updateHeader() {
    if (window.scrollY > 80) {
      header.classList.add("is-scrolled");
    } else {
      header.classList.remove("is-scrolled");
    }
  }

  updateHeader();

  window.addEventListener("scroll", updateHeader);
});
