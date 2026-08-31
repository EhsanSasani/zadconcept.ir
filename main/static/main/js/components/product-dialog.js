(function () {
  const modal = document.querySelector("[data-product-modal]");
  if (!modal) return;

  const modalImage = modal.querySelector("[data-modal-image]");
  const modalType = modal.querySelector("[data-modal-type]");
  const modalTitle = modal.querySelector("[data-modal-title]");
  const modalCode = modal.querySelector("[data-modal-code]");
  const modalPrice = modal.querySelector("[data-modal-price]");
  const modalDescription = modal.querySelector("[data-modal-description]");
  const modalStock = modal.querySelector("[data-modal-stock]");
  const modalContact = modal.querySelector("[data-modal-contact]");
  const modalDialog = modal.querySelector('[role="dialog"]');
  const closeButton = modal.querySelector(".zad-product-modal__close");
  let opener = null;

  const typeLabels = {
    "hand-bouquet": "HAND BOUQUET",
    "box": "BOX",
    "bouquet": "BOUQUET",
    "jarl": "JARL",
    "wedding": "WEDDING",
    "wedding-car": "WEDDING CAR",
    "bridal-bouquet": "BRIDAL BOUQUET",
    "proposal-bale-boroon-bouquet": "PROPOSAL BOUQUET",
    "proposal-bale-boroon-sweets": "PROPOSAL SWEETS",
    "stand": "STAND",
    "plants": "PLANTS",
    "bakery": "BAKERY",
    "gifts": "GIFTS",
    "event": "EVENT",
  };

  function getTypeLabel(value) {
    return typeLabels[value] || value || "COLLECTION";
  }

  function openModal(card) {
    card = card.closest("[data-catalog-card]") || card;
    opener = document.activeElement;
    const image = card.querySelector("[data-product-image]");

    const imageSrc = image ? image.getAttribute("src") : "";
    const imageAlt = image ? image.getAttribute("alt") : "";

    const type = getTypeLabel(card.dataset.productType);
    const code = (card.dataset.productCode || "").trim();
    const name = (card.dataset.productName || "").trim();
    const price = card.dataset.productPrice || "استعلام قیمت";
    const description = card.dataset.productDescription || "";
    const stock = card.dataset.productStock || "";
    const contact = card.dataset.productContact || "";

    if (modalImage) {
      modalImage.src = imageSrc;
      modalImage.alt = imageAlt;
    }

    if (modalType) {
      modalType.textContent = type;
    }

    if (modalTitle) {
      modalTitle.textContent = name || code || "ZAD";
    }

    if (modalCode) {
      const showCodeBelowName = Boolean(name && code);
      modalCode.textContent = showCodeBelowName ? code : "";
      modalCode.hidden = !showCodeBelowName;
    }

    if (modalPrice) {
      modalPrice.textContent = price;
    }

    if (modalDescription) {
      modalDescription.textContent = description;
      modalDescription.hidden = !description;
    }

    if (modalStock) {
      modalStock.textContent = stock;
      modalStock.hidden = !stock;
    }

    if (modalContact) {
      modalContact.textContent = contact || "برای قیمت و ثبت سفارش با ما در ارتباط باشید.";
    }

    modal.hidden = false;
    document.body.style.overflow = "hidden";
    window.requestAnimationFrame(function () {
      (closeButton || modalDialog).focus();
    });
  }

  function closeModal() {
    modal.hidden = true;
    document.body.style.overflow = "";

    if (modalImage) {
      modalImage.src = "";
      modalImage.alt = "";
    }

    if (modalCode) {
      modalCode.textContent = "";
      modalCode.hidden = true;
    }

    if (modalDescription) {
      modalDescription.textContent = "";
      modalDescription.hidden = true;
    }

    if (opener && typeof opener.focus === "function") {
      opener.focus();
    }
    opener = null;
  }

  function focusableItems() {
    return Array.from(
      modal.querySelectorAll(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    ).filter(function (item) {
      return !item.hidden;
    });
  }

  document.addEventListener("click", function (event) {
    const card = event.target.closest("[data-zad-modal-card]");

    if (card) {
      event.preventDefault();
      openModal(card);
      return;
    }

    if (event.target.closest("[data-product-modal-close]")) {
      closeModal();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !modal.hidden) {
      event.preventDefault();
      closeModal();
      return;
    }

    if (event.key === "Tab" && !modal.hidden) {
      const items = focusableItems();
      if (!items.length) {
        event.preventDefault();
        modalDialog.focus();
        return;
      }

      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });
})();

(() => {
  const modal = document.querySelector("[data-product-modal]");
  if (!modal) return;

  const modalImage = modal.querySelector("[data-modal-image]");
  if (!modalImage) return;

  const viewer = document.createElement("div");
  viewer.className = "zad-product-image-viewer";
  viewer.hidden = true;
  viewer.setAttribute("role", "dialog");
  viewer.setAttribute("aria-modal", "true");
  viewer.setAttribute("aria-hidden", "true");
  viewer.setAttribute("aria-label", "نمایش تمام صفحه تصویر محصول");

  const viewerImage = document.createElement("img");
  viewerImage.className = "zad-product-image-viewer__image";
  viewerImage.alt = "";
  viewerImage.decoding = "async";
  viewerImage.draggable = false;

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.className = "zad-product-image-viewer__close";
  closeButton.setAttribute("aria-label", "بستن تصویر تمام صفحه");

  viewer.append(viewerImage, closeButton);
  document.body.appendChild(viewer);

  modalImage.setAttribute("role", "button");
  modalImage.setAttribute("tabindex", "0");
  modalImage.setAttribute("aria-haspopup", "dialog");
  modalImage.setAttribute("aria-expanded", "false");

  let closeTimer = null;

  function viewerIsOpen() {
    return !viewer.hidden && viewer.classList.contains("is-open");
  }

  function openViewer() {
    const src = modalImage.getAttribute("src");
    if (!src) return;

    if (closeTimer) {
      window.clearTimeout(closeTimer);
      closeTimer = null;
    }

    viewerImage.src = src;
    viewerImage.alt = modalImage.alt || "";
    viewer.hidden = false;
    viewer.setAttribute("aria-hidden", "false");
    modalImage.setAttribute("aria-expanded", "true");

    window.requestAnimationFrame(function () {
      viewer.classList.add("is-open");
      closeButton.focus({ preventScroll: true });
    });
  }

  function closeViewer(options) {
    if (viewer.hidden) return;

    const settings = options || {};
    viewer.classList.remove("is-open");
    viewer.setAttribute("aria-hidden", "true");
    modalImage.setAttribute("aria-expanded", "false");

    if (closeTimer) {
      window.clearTimeout(closeTimer);
    }

    const finish = function () {
      viewer.hidden = true;
      viewerImage.removeAttribute("src");
      viewerImage.alt = "";
      closeTimer = null;

      if (settings.restoreFocus !== false && !modal.hidden) {
        modalImage.focus({ preventScroll: true });
      }
    };

    if (settings.immediate) {
      finish();
      return;
    }

    closeTimer = window.setTimeout(finish, 220);
  }

  modalImage.addEventListener("click", openViewer);
  modalImage.addEventListener("keydown", function (event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openViewer();
    }
  });

  closeButton.addEventListener("click", function () {
    closeViewer();
  });

  viewer.addEventListener("click", function (event) {
    if (event.target === viewer) {
      closeViewer();
    }
  });

  document.addEventListener(
    "keydown",
    function (event) {
      if (!viewerIsOpen()) return;

      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeViewer();
        return;
      }

      if (event.key === "Tab") {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeButton.focus({ preventScroll: true });
      }
    },
    true
  );

  document.addEventListener(
    "click",
    function (event) {
      if (!viewer.hidden && event.target.closest("[data-product-modal-close]")) {
        closeViewer({ restoreFocus: false, immediate: true });
      }
    },
    true
  );
})();
