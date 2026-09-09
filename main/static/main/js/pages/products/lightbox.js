(function () {
  "use strict";
  const trigger = document.querySelector('[data-product-main]');
  const overlays = window.ZadOverlays;
  if (!trigger || !overlays) return;
  const thumbs = Array.from(document.querySelectorAll('[data-product-thumb]'));
  const lightbox = document.createElement('div');
  lightbox.className = 'product-image-lightbox';
  lightbox.id = 'product-image-lightbox';
  lightbox.hidden = true;
  lightbox.setAttribute('role', 'dialog');
  lightbox.setAttribute('aria-modal', 'true');
  lightbox.setAttribute('aria-label', 'تصاویر محصول');

  const image = document.createElement('img');
  image.className = 'product-image-lightbox__image';
  image.decoding = 'async';
  image.draggable = false;
  const button = (className, label, text) => {
    const element = document.createElement('button');
    element.type = 'button';
    element.className = className;
    element.setAttribute('aria-label', label);
    if (text) { const glyph = document.createElement('span'); glyph.textContent = text; glyph.setAttribute('aria-hidden', 'true'); element.appendChild(glyph); }
    return element;
  };
  const closeButton = button('product-image-lightbox__close', 'بستن تصویر');
  const previousButton = button('product-image-lightbox__step product-image-lightbox__step--previous', 'تصویر قبلی', '‹');
  const nextButton = button('product-image-lightbox__step product-image-lightbox__step--next', 'تصویر بعدی', '›');
  const counter = document.createElement('p');
  counter.className = 'product-image-lightbox__counter';
  counter.setAttribute('role', 'status');
  counter.setAttribute('aria-live', 'polite');
  lightbox.append(image, closeButton, previousButton, nextButton, counter);
  document.body.appendChild(lightbox);
  previousButton.hidden = nextButton.hidden = thumbs.length < 2;
  counter.hidden = thumbs.length < 2;
  let selected = Math.max(0, thumbs.findIndex((thumb) => thumb.classList.contains('is-active')));

  trigger.classList.add('product-image-lightbox__trigger');
  trigger.setAttribute('role', 'button');
  trigger.tabIndex = 0;
  trigger.setAttribute('aria-haspopup', 'dialog');
  trigger.setAttribute('aria-controls', lightbox.id);
  trigger.setAttribute('aria-expanded', 'false');

  function labelTrigger() {
    trigger.setAttribute('aria-label', `${trigger.alt || 'تصویر محصول'}؛ نمایش تمام‌صفحه`);
  }
  function updateFullImage() {
    image.src = trigger.getAttribute('src') || trigger.currentSrc;
    image.alt = trigger.alt || 'تصویر محصول';
    counter.textContent = `${new Intl.NumberFormat('fa').format(selected + 1)} از ${new Intl.NumberFormat('fa').format(thumbs.length)}`;
  }
  function select(index) {
    if (!thumbs.length) return;
    selected = (index + thumbs.length) % thumbs.length;
    const thumb = thumbs[selected];
    const source = thumb.querySelector('img');
    trigger.src = thumb.href;
    trigger.alt = source?.alt || '';
    const srcset = source?.getAttribute('srcset');
    if (srcset) trigger.setAttribute('srcset', srcset);
    else trigger.removeAttribute('srcset');
    thumbs.forEach((item, itemIndex) => {
      const active = itemIndex === selected;
      item.classList.toggle('is-active', active);
      if (active) item.setAttribute('aria-current', 'true');
      else item.removeAttribute('aria-current');
    });
    labelTrigger();
    if (!lightbox.hidden) updateFullImage();
  }
  function closeLightbox() {
    if (lightbox.hidden) return;
    overlays.close(lightbox);
    lightbox.hidden = true;
    image.removeAttribute('src');
    trigger.setAttribute('aria-expanded', 'false');
  }
  function openLightbox() {
    if (!lightbox.hidden) return;
    updateFullImage();
    lightbox.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    overlays.open(lightbox, { focus: closeButton, onClose: closeLightbox, opener: trigger });
  }
  labelTrigger();
  thumbs.forEach((thumb, index) => thumb.addEventListener('click', (event) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    select(index);
  }));
  trigger.addEventListener('click', openLightbox);
  trigger.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openLightbox(); }
  });
  previousButton.addEventListener('click', () => select(selected - 1));
  nextButton.addEventListener('click', () => select(selected + 1));
  closeButton.addEventListener('click', closeLightbox);
  lightbox.addEventListener('click', (event) => { if (event.target === lightbox) closeLightbox(); });
  lightbox.addEventListener('keydown', (event) => {
    if (thumbs.length < 2 || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      select(selected + (event.key === 'ArrowRight' ? 1 : -1));
    }
  });
})();
