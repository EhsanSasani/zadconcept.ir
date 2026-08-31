(() => {
  const trigger = document.querySelector('.item-detail__image-frame > img');
  if (!trigger) return;

  const lightbox = document.createElement('div');
  lightbox.className = 'product-image-lightbox';
  lightbox.id = 'product-image-lightbox';
  lightbox.setAttribute('role', 'dialog');
  lightbox.setAttribute('aria-modal', 'true');
  lightbox.setAttribute('aria-hidden', 'true');
  lightbox.setAttribute('aria-label', trigger.alt || 'تصویر محصول');

  const image = document.createElement('img');
  image.className = 'product-image-lightbox__image';
  image.alt = trigger.alt || '';
  image.decoding = 'async';
  image.draggable = false;

  const closeButton = document.createElement('button');
  closeButton.type = 'button';
  closeButton.className = 'product-image-lightbox__close';
  closeButton.setAttribute('aria-label', 'بستن تصویر');
  closeButton.innerHTML = '<span aria-hidden="true"></span>';

  lightbox.append(image, closeButton);
  document.body.appendChild(lightbox);

  trigger.classList.add('product-image-lightbox__trigger');
  trigger.setAttribute('role', 'button');
  trigger.setAttribute('tabindex', '0');
  trigger.setAttribute('aria-haspopup', 'dialog');
  trigger.setAttribute('aria-controls', lightbox.id);
  trigger.setAttribute('aria-expanded', 'false');
  trigger.setAttribute('aria-label', `${trigger.alt || 'تصویر محصول'}؛ نمایش تمام‌صفحه`);

  let lastFocusedElement = null;
  let scrollY = 0;
  let bodyStyleSnapshot = null;

  const getOriginalImageSrc = () => {
    const src = trigger.getAttribute('src');
    return src ? new URL(src, document.baseURI).href : trigger.currentSrc;
  };

  const lockPage = () => {
    scrollY = window.scrollY;
    bodyStyleSnapshot = {
      position: document.body.style.position,
      top: document.body.style.top,
      left: document.body.style.left,
      right: document.body.style.right,
      width: document.body.style.width,
    };

    document.documentElement.classList.add('has-product-image-lightbox');
    document.body.classList.add('has-product-image-lightbox');
    document.body.style.position = 'fixed';
    document.body.style.top = `-${scrollY}px`;
    document.body.style.left = '0';
    document.body.style.right = '0';
    document.body.style.width = '100%';
  };

  const unlockPage = () => {
    document.documentElement.classList.remove('has-product-image-lightbox');
    document.body.classList.remove('has-product-image-lightbox');

    if (bodyStyleSnapshot) {
      document.body.style.position = bodyStyleSnapshot.position;
      document.body.style.top = bodyStyleSnapshot.top;
      document.body.style.left = bodyStyleSnapshot.left;
      document.body.style.right = bodyStyleSnapshot.right;
      document.body.style.width = bodyStyleSnapshot.width;
    }

    window.scrollTo(0, scrollY);
    bodyStyleSnapshot = null;
  };

  const openLightbox = () => {
    if (lightbox.classList.contains('is-open')) return;

    lastFocusedElement = document.activeElement;
    image.src = getOriginalImageSrc();
    image.alt = trigger.alt || '';

    lockPage();
    lightbox.setAttribute('aria-hidden', 'false');
    trigger.setAttribute('aria-expanded', 'true');

    window.requestAnimationFrame(() => {
      lightbox.classList.add('is-open');
      closeButton.focus({ preventScroll: true });
    });
  };

  const closeLightbox = () => {
    if (!lightbox.classList.contains('is-open')) return;

    lightbox.classList.remove('is-open');
    lightbox.setAttribute('aria-hidden', 'true');
    trigger.setAttribute('aria-expanded', 'false');
    unlockPage();

    if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
      lastFocusedElement.focus({ preventScroll: true });
    }
    lastFocusedElement = null;
  };

  trigger.addEventListener('click', openLightbox);
  trigger.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openLightbox();
    }
  });

  closeButton.addEventListener('click', closeLightbox);
  lightbox.addEventListener('click', (event) => {
    if (event.target === lightbox) {
      closeLightbox();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (!lightbox.classList.contains('is-open')) return;

    if (event.key === 'Escape') {
      event.preventDefault();
      closeLightbox();
      return;
    }

    if (event.key === 'Tab') {
      event.preventDefault();
      closeButton.focus({ preventScroll: true });
    }
  });
})();
