(function () {
  "use strict";
  const modal = document.querySelector("[data-product-modal]");
  const overlays = window.ZadOverlays;
  if (!modal || !overlays) return;
  const dialog = modal.querySelector('[role="dialog"]');
  const image = modal.querySelector("[data-modal-image]");
  if (!dialog || !image) return;
  const closeButton = modal.querySelector(".zad-product-modal__close");
  const detailLink = modal.querySelector("[data-modal-detail]");
  const labels = { "hand-bouquet": "HAND BOUQUET", box: "BOX", bouquet: "BOUQUET", jarl: "JAR", wedding: "WEDDING", "wedding-car": "WEDDING CAR", "bridal-bouquet": "BRIDAL BOUQUET", "proposal-bale-boroon-bouquet": "PROPOSAL BOUQUET", "proposal-bale-boroon-sweets": "PROPOSAL SWEETS", stand: "STAND", plants: "PLANTS", bakery: "BAKERY", gifts: "GIFTS", event: "EVENT" };

  const viewer = document.createElement("div");
  viewer.className = "zad-product-image-viewer";
  viewer.hidden = true;
  viewer.setAttribute("role", "dialog");
  viewer.setAttribute("aria-modal", "true");
  viewer.setAttribute("aria-label", "نمایش تمام‌صفحه تصویر محصول");
  const fullImage = document.createElement("img");
  fullImage.className = "zad-product-image-viewer__image";
  fullImage.decoding = "async";
  fullImage.alt = "";
  const viewerClose = document.createElement("button");
  viewerClose.type = "button";
  viewerClose.className = "zad-product-image-viewer__close";
  viewerClose.setAttribute("aria-label", "بستن تصویر تمام‌صفحه");
  viewer.append(fullImage, viewerClose);
  document.body.appendChild(viewer);
  image.setAttribute("role", "button");
  image.tabIndex = 0;
  image.setAttribute("aria-haspopup", "dialog");
  image.setAttribute("aria-expanded", "false");

  function setText(selector, text, optional = false) {
    const element = modal.querySelector(selector);
    if (!element) return;
    element.textContent = text;
    if (optional) element.hidden = !text;
  }

  function closeViewer() {
    if (viewer.hidden) return;
    overlays.close(viewer);
    viewer.hidden = true;
    viewer.classList.remove("is-open");
    fullImage.removeAttribute("src");
    image.setAttribute("aria-expanded", "false");
  }

  function closeModal() {
    if (modal.hidden) return;
    closeViewer();
    overlays.close(modal);
    modal.hidden = true;
    image.removeAttribute("src");
    image.removeAttribute("srcset");
    image.alt = "";
  }

  function openModal(link) {
    const card = link.closest("[data-catalog-card]");
    if (!card) return;
    const source = card.querySelector("[data-product-image]");
    const data = card.dataset;
    const name = (data.productName || "").trim();
    const code = (data.productCode || "").trim();
    image.hidden = !source;
    if (source) {
      image.src = source.getAttribute("src") || source.currentSrc;
      image.alt = source.alt || name || code;
      image.setAttribute("aria-label", `${image.alt}؛ نمایش تمام‌صفحه`);
      const srcset = source.getAttribute("srcset");
      if (srcset) image.setAttribute("srcset", srcset);
      else image.removeAttribute("srcset");
      image.sizes = "(max-width: 760px) 100vw, 55vw";
    }
    setText("[data-modal-type]", labels[data.productType] || data.productType || "COLLECTION");
    setText("[data-modal-title]", name || code || "ZAD");
    setText("[data-modal-code]", name && code ? code : "", true);
    setText("[data-modal-price]", data.productPrice || "استعلام قیمت");
    setText("[data-modal-description]", data.productDescription || "", true);
    setText("[data-modal-stock]", data.productStock || "", true);
    setText("[data-modal-contact]", data.productContact || "برای قیمت و ثبت سفارش با ما در ارتباط باشید.");
    if (detailLink) detailLink.href = link.href;
    if (data.productDescription) dialog.setAttribute("aria-describedby", "zad-product-modal-description");
    else dialog.removeAttribute("aria-describedby");
    modal.hidden = false;
    overlays.open(modal, { focus: closeButton, onClose: closeModal, opener: link });
  }

  function openViewer() {
    if (!image.getAttribute("src") || !viewer.hidden) return;
    fullImage.src = image.getAttribute("src");
    fullImage.draggable = false;
    fullImage.alt = image.alt;
    viewer.hidden = false;
    viewer.classList.add("is-open");
    image.setAttribute("aria-expanded", "true");
    overlays.open(viewer, { focus: viewerClose, onClose: closeViewer });
  }
  image.addEventListener("click", openViewer);
  image.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openViewer(); }
  });
  viewerClose.addEventListener("click", closeViewer);
  viewer.addEventListener("click", (event) => { if (event.target === viewer) closeViewer(); });
  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-zad-modal-card]");
    if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) {
      event.preventDefault();
      openModal(link);
    } else if (event.target.closest("[data-product-modal-close]")) closeModal();
  });
})();
