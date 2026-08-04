export function initProductDialog() {
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
  const closeButton = modal.querySelector("[data-product-modal-close-button]");
  const fallbackDescription = modalDescription?.textContent.trim() || "";
  let opener = null;
  let previousBodyOverflow = "";
  let bodyHadDialogClass = false;
  let backgroundState = [];

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

  function setBackgroundInert(isInert) {
    if (isInert) {
      backgroundState = Array.from(document.body.children)
        .filter((element) => element !== modal && element.tagName !== "SCRIPT")
        .map((element) => ({
          element,
          hadInert: element.hasAttribute("inert"),
        }));
      backgroundState.forEach(({ element }) => element.setAttribute("inert", ""));
      return;
    }

    backgroundState.forEach(({ element, hadInert }) => {
      if (!hadInert) element.removeAttribute("inert");
    });
    backgroundState = [];
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
      modalDescription.textContent = description || fallbackDescription;
      modalDescription.hidden = false;
    }

    if (modalStock) {
      modalStock.textContent = stock;
      modalStock.hidden = !stock;
    }

    if (modalContact) {
      modalContact.textContent = contact || "برای قیمت و ثبت سفارش با ما در ارتباط باشید.";
    }

    previousBodyOverflow = document.body.style.overflow;
    bodyHadDialogClass = document.body.classList.contains("has-open-product-dialog");
    setBackgroundInert(true);
    document.body.classList.add("has-open-product-dialog");
    document.body.style.overflow = "hidden";
    modal.hidden = false;
    window.requestAnimationFrame(function () {
      (closeButton || modalDialog).focus();
    });
  }

  function closeModal() {
    if (modal.hidden) return;
    modal.hidden = true;
    setBackgroundInert(false);
    document.body.style.overflow = previousBodyOverflow;
    if (!bodyHadDialogClass) document.body.classList.remove("has-open-product-dialog");

    if (modalImage) {
      modalImage.src = "";
      modalImage.alt = "";
    }

    if (modalDescription) {
      modalDescription.textContent = fallbackDescription;
      modalDescription.hidden = false;
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
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }
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
      if (!modal.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  document.addEventListener("focusin", function (event) {
    if (modal.hidden || modal.contains(event.target)) return;
    const items = focusableItems();
    (items[0] || modalDialog).focus();
  });
}

initProductDialog();
