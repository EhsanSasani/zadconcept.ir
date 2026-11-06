/* Restore private workspace navigation only; never cache forms or server records. */
(() => {
  'use strict';
  const key = 'zad-panel-navigation:v1';
  const user = document.body.dataset.panelUser;
  const ttl = 30 * 60 * 1000;
  const backSelector = '[data-app-back], [data-panel-back], .panel-back, .detail-back, a[aria-label^="بازگشت"]';
  const route = value => {
    if (typeof value !== 'string' || !value) return null;
    try {
      const url = new URL(value, location.href);
      if (url.origin !== location.origin || !/^\/(studio|sales|procurement|team|panel)\//.test(url.pathname)
          || /\/(login|logout|delete|void|status|select)\/$/.test(url.pathname)) return null;
      return url.pathname + url.search;
    } catch { return null; }
  };
  let store;
  try { store = JSON.parse(sessionStorage.getItem(key)); } catch { /* Storage can be blocked. */ }
  if (!user) {
    try { sessionStorage.removeItem(key); } catch { /* Ordinary links still work. */ }
    return;
  }
  if (!store || store.user !== user || !Array.isArray(store.pages)) store = { user, pages: [] };
  store.pages = store.pages.filter(page => page && route(page.url) === page.url
    && Number.isFinite(page.at) && Date.now() - page.at >= 0 && Date.now() - page.at < ttl).slice(-30);
  const write = () => { try { sessionStorage.setItem(key, JSON.stringify(store)); } catch { /* No dependency on storage. */ } };
  const find = url => store.pages.find(page => page.url === url);
  let endingSession = false;
  let displayed = route(location.href);
  if (!displayed) return;
  const cached = find(displayed);
  const pending = store.pending;
  delete store.pending;
  const fresh = pending && Number.isFinite(pending.at) && Date.now() - pending.at >= 0 && Date.now() - pending.at < 60000;
  const type = performance.getEntriesByType?.('navigation')[0]?.type;
  let restore = type === 'back_forward' || (fresh && pending.kind === 'return' && pending.target === displayed);
  let parent = (restore || type === 'reload') ? route(cached?.parent) : null;
  if (fresh && pending.kind === 'link' && pending.target === displayed) {
    const from = route(pending.from);
    parent = from && from.split('?')[0] === displayed.split('?')[0] && !pending.drilldown
      ? route(pending.parent) : from;
  }
  if (fresh && pending.kind === 'submit' && route(document.referrer) === pending.from) {
    if (route(pending.returnTarget) === displayed) restore = true;
    parent = route(pending.parent);
    if (parent === displayed) parent = route(cached?.parent);
  }
  if (parent === displayed) parent = null;
  write();
  const quick = () => [...document.querySelectorAll('[data-quick-filter]')]
    .map(group => group.querySelector('[aria-pressed="true"]')?.dataset.productionFilter || 'all');
  const save = () => {
    if (endingSession) return;
    const page = { url: displayed, at: Date.now(), parent,
      x: window.scrollX, y: window.scrollY, quick: quick(),
      open: [...document.querySelectorAll('details[id][open]')].map(node => node.id).slice(0, 30),
      tables: [...document.querySelectorAll('.table-scroll')].map(node => node.scrollLeft).slice(0, 10) };
    store.pages = [...store.pages.filter(item => item.url !== displayed), page].slice(-30);
    write();
  };
  const mark = value => { if (!endingSession) { store.pending = { ...value, at: Date.now() }; write(); } };
  const restoreQuick = values => {
    if (!Array.isArray(values)) return;
    document.querySelectorAll('[data-quick-filter]').forEach((group, index) => {
      const value = values[index];
      if (!['all', 'DAILY', 'CUSTOM'].includes(value)) return;
      const button = group.querySelector(`[data-production-filter="${value}"]`);
      if (button?.getAttribute('aria-pressed') !== 'true') button?.click();
    });
  };
  const position = value => Number.isFinite(value) && Math.abs(value) <= 2000000 ? value : 0;
  let interrupted = false;
  ['pointerdown', 'wheel', 'touchstart', 'keydown'].forEach(name =>
    window.addEventListener(name, () => { interrupted = true; }, { passive: true }));
  const apply = () => {
    if (!restore || interrupted || !cached) return;
    restoreQuick(cached.quick);
    if (Array.isArray(cached.open)) cached.open.forEach(id => {
      const node = document.getElementById(id);
      if (node?.tagName === 'DETAILS') node.open = true;
    });
    if (Array.isArray(cached.tables)) document.querySelectorAll('.table-scroll').forEach((node, index) => {
      node.scrollLeft = position(cached.tables[index]);
    });
    window.scrollTo({ left: position(cached.x), top: position(cached.y), behavior: 'instant' });
  };
  document.querySelectorAll(backSelector).forEach(link => {
    if (parent) link.href = parent;
  });
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[href]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey
        || event.shiftKey || event.altKey || link.hasAttribute('download')
        || (link.target && link.target !== '_self')) return;
    const target = route(link.href);
    if (!target || target === displayed) return;
    save();
    if (link.matches(backSelector)) mark({ kind: 'return', target });
    else if (link.closest('main')) mark({ kind: 'link', target, from: displayed, parent,
      drilldown: link.matches('[data-panel-drilldown]') });
    else { delete store.pending; write(); }
  });
  const decorate = () => document.querySelectorAll('form[data-panel-return]').forEach(form => {
    const target = form.dataset.panelReturn === 'self' ? displayed : parent;
    let input = form.querySelector('input[name="return_to"]');
    if (!input) {
      input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'return_to';
      form.appendChild(input);
    }
    input.value = target || '';
  });
  const submitted = form => {
    if (form.method.toLowerCase() !== 'post') return;
    const action = new URL(form.getAttribute('action') || location.href, location.href);
    if (action.origin !== location.origin) return;
    if (action.pathname === '/studio/logout/') {
      endingSession = true;
      store = { user, pages: [] };
      try { sessionStorage.removeItem(key); } catch { /* Login also clears state. */ }
      return;
    }
    save();
    mark({ kind: 'submit', from: displayed, parent,
      returnTarget: route(form.querySelector?.('input[name="return_to"]')?.value) });
  };
  decorate();
  document.addEventListener('submit', event => {
    if (!event.defaultPrevented) submitted(event.target);
  });
  document.addEventListener('panel:submit', event => submitted(event.detail));
  document.addEventListener('panel:save', save);
  document.addEventListener('panel:table-ready', () => {
    const selected = find(displayed)?.quick;
    displayed = route(location.href);
    decorate();
    requestAnimationFrame(() => restoreQuick(selected));
  });
  window.addEventListener('popstate', () => {
    save();
    mark({ kind: 'return', target: route(location.href) });
  });
  window.addEventListener('pagehide', save);
  window.addEventListener('pageshow', event => {
    if (event.persisted) {
      mark({ kind: 'return', target: displayed });
      restore = true;
    }
    requestAnimationFrame(() => requestAnimationFrame(apply));
  });
  window.addEventListener('load', apply);
})();
