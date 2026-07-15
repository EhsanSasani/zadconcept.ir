(function () {
  const modal = document.querySelector("[data-product-modal]");
  if (!modal) return;

  const modalImage = modal.querySelector("[data-modal-image]");
  const modalType = modal.querySelector("[data-modal-type]");
  const modalTitle = modal.querySelector("[data-modal-title]");
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
    const code = card.dataset.productCode || "";
    const name = card.dataset.productName || "";
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
