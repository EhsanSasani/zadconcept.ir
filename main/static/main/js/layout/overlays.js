/* Shared modal lifecycle: nested overlays preserve the page and keyboard focus. */
(function () {
  "use strict";
  const stack = [];
  const inertSnapshot = new Map();
  let scrollSnapshot = null;
  let bodySnapshot = null;
  let scrollPosition = null;
  const selector = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function restoreInert() {
    inertSnapshot.forEach((value, element) => { element.inert = value; });
    inertSnapshot.clear();
  }

  function isolate(root) {
    restoreInert();
    for (let node = root; node && node !== document.body; node = node.parentElement) {
      Array.from(node.parentElement?.children || []).forEach((sibling) => {
        if (sibling === node || /^(SCRIPT|STYLE|LINK|TEMPLATE)$/.test(sibling.tagName)) return;
        inertSnapshot.set(sibling, sibling.inert);
        sibling.inert = true;
      });
    }
  }

  function updateViewport() {
    if (!stack.length) return;
    const viewport = window.visualViewport;
    document.documentElement.style.setProperty('--zad-overlay-height', `${viewport?.height || window.innerHeight}px`);
    document.documentElement.style.setProperty('--zad-overlay-top', `${viewport?.offsetTop || 0}px`);
  }

  function lockScroll() {
    scrollPosition = { x: window.scrollX, y: window.scrollY };
    bodySnapshot = {};
    ['position', 'top', 'left', 'right', 'width'].forEach((property) => {
      bodySnapshot[property] = document.body.style[property];
    });
    scrollSnapshot = [document.documentElement, document.body].map((element) => ({
      element, overflow: element.style.overflow, overscroll: element.style.overscrollBehavior,
    }));
    scrollSnapshot.forEach(({ element }) => {
      element.style.overflow = 'hidden';
      element.style.overscrollBehavior = 'none';
    });
    // Fixed body also prevents background rubber-banding on touch Safari.
    Object.assign(document.body.style, {
      position: 'fixed', top: `-${scrollPosition.y}px`, left: '0', right: '0', width: '100%',
    });
  }

  function unlockScroll() {
    (scrollSnapshot || []).forEach(({ element, overflow, overscroll }) => {
      element.style.overflow = overflow;
      element.style.overscrollBehavior = overscroll;
    });
    if (bodySnapshot) Object.assign(document.body.style, bodySnapshot);
    if (scrollPosition) {
      const behavior = document.documentElement.style.scrollBehavior;
      document.documentElement.style.scrollBehavior = 'auto';
      window.scrollTo(scrollPosition.x, scrollPosition.y);
      document.documentElement.style.scrollBehavior = behavior;
    }
    bodySnapshot = null;
    scrollPosition = null;
    scrollSnapshot = null;
    document.documentElement.style.removeProperty('--zad-overlay-height');
    document.documentElement.style.removeProperty('--zad-overlay-top');
  }

  function items(entry) {
    return Array.from(entry.root.querySelectorAll(selector)).filter((element) =>
      !element.closest('[hidden], [inert]') && element.getClientRects().length > 0
      && window.getComputedStyle(element).visibility !== 'hidden'
    );
  }

  function focusEntry(entry) {
    const target = entry.focus || items(entry)[0] || entry.root;
    if (!target.hasAttribute('tabindex') && target === entry.root) target.tabIndex = -1;
    target.focus({ preventScroll: true });
  }

  window.ZadOverlays = {
    open(root, options = {}) {
      if (stack.some((entry) => entry.root === root)) return;
      if (!stack.length) lockScroll();
      const entry = { root, opener: document.activeElement, ...options };
      stack.push(entry);
      isolate(root);
      updateViewport();
      focusEntry(entry);
    },
    close(root, { restoreFocus = true } = {}) {
      const index = stack.findIndex((entry) => entry.root === root);
      if (index < 0) return;
      const [entry] = stack.splice(index, 1);
      const active = stack[stack.length - 1];
      if (active) isolate(active.root);
      else { restoreInert(); unlockScroll(); }
      if (restoreFocus && entry.opener?.isConnected && !entry.opener.closest('[hidden], [inert]')) {
        entry.opener.focus({ preventScroll: true });
      } else if (active && !active.root.contains(document.activeElement)) focusEntry(active);
    },
    reducedMotion: () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  };

  document.addEventListener('keydown', (event) => {
    const entry = stack[stack.length - 1];
    if (!entry) return;
    if (event.key === 'Escape' && entry.onClose) {
      event.preventDefault();
      event.stopImmediatePropagation();
      entry.onClose();
    } else if (event.key === 'Tab') {
      const controls = items(entry);
      const first = controls[0];
      const last = controls[controls.length - 1];
      const current = document.activeElement;
      if (!controls.length) { event.preventDefault(); focusEntry(entry); }
      else if (event.shiftKey && (current === first || !controls.includes(current))) {
        event.preventDefault(); last.focus({ preventScroll: true });
      } else if (!event.shiftKey && (current === last || !controls.includes(current))) {
        event.preventDefault(); first.focus({ preventScroll: true });
      }
    }
  }, true);

  document.addEventListener('focusin', (event) => {
    const entry = stack[stack.length - 1];
    if (entry && !entry.root.contains(event.target)) focusEntry(entry);
  });
  window.visualViewport?.addEventListener('resize', updateViewport);
  window.visualViewport?.addEventListener('scroll', updateViewport);
  window.addEventListener('resize', updateViewport, { passive: true });
})();
