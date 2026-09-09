/* Progressive admin enhancements. Django remains responsible for saves,
   permissions, validation, file processing and destructive-action confirmation. */
(() => {
  'use strict';
  const ready = () => {
    const mobile = window.matchMedia('(max-width: 991.98px)');
    const sidebar = document.querySelector('.zad-sidebar');
    const trigger = document.querySelector('[data-lte-toggle="sidebar"]');
    const backdrop = document.querySelector('.zad-menu-backdrop');
    let previousFocus = null;
    const inertBefore = new Map();
    const setMenu = (open) => {
      if (!sidebar) return;
      const active = open && mobile.matches;
      document.body.classList.toggle('zad-menu-open', active);
      document.body.classList.remove('sidebar-open');
      if (trigger) trigger.setAttribute('aria-expanded', String(active || !mobile.matches));
      sidebar.inert = mobile.matches && !active;
      if (backdrop) backdrop.hidden = !active;
      if (active) {
        previousFocus = document.activeElement;
        document.querySelectorAll('.app-main, .app-header, .app-footer').forEach(node => {
          if (!inertBefore.has(node)) inertBefore.set(node, node.inert);
          node.inert = true;
        });
        sidebar.querySelector('.zad-menu-close')?.focus();
      } else {
        inertBefore.forEach((value, node) => { node.inert = value; });
        inertBefore.clear();
        if (previousFocus && mobile.matches) previousFocus.focus();
        previousFocus = null;
      }
    };
    if (sidebar && trigger) {
      trigger.removeAttribute('data-lte-toggle');
      trigger.setAttribute('aria-label', 'باز کردن منوی مدیریت');
      trigger.setAttribute('aria-controls', 'jazzy-sidebar');
      trigger.addEventListener('click', event => {
        event.preventDefault();
        if (mobile.matches) setMenu(!document.body.classList.contains('zad-menu-open'));
      });
      trigger.addEventListener('keydown', event => {
        if (event.key === ' ') { event.preventDefault(); trigger.click(); }
      });
      sidebar.querySelector('.zad-menu-close')?.addEventListener('click', () => setMenu(false));
      backdrop?.addEventListener('click', () => setMenu(false));
      mobile.addEventListener('change', () => setMenu(false));
      document.addEventListener('keydown', event => {
        if (!document.body.classList.contains('zad-menu-open')) return;
        if (event.key === 'Escape') { event.preventDefault(); setMenu(false); return; }
        if (event.key !== 'Tab') return;
        const nodes = [...sidebar.querySelectorAll('a[href], button, input, summary')].filter(el => !el.disabled && el.getClientRects().length);
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      });
      setMenu(false);
    }

    const menuSearch = document.querySelector('#zad-menu-search');
    const normalize = text => text.replace(/ي/g, 'ی').replace(/ك/g, 'ک').toLowerCase().trim();
    menuSearch?.addEventListener('input', () => {
      const query = normalize(menuSearch.value);
      let found = false;
      document.querySelectorAll('.zad-nav-group').forEach(group => {
        if (!group.hasAttribute('data-original-open')) group.dataset.originalOpen = group.open ? 'yes' : 'no';
        let visible = false;
        group.querySelectorAll('[data-menu-item]').forEach(item => {
          item.hidden = !!query && !normalize(item.textContent + ' ' + group.querySelector('summary').textContent).includes(query);
          if (!item.hidden) visible = true;
        });
        group.hidden = !visible;
        group.open = query ? visible : group.dataset.originalOpen === 'yes';
        if (visible) found = true;
      });
      const empty = document.querySelector('.zad-menu-empty');
      if (empty) empty.hidden = found;
    });

    // Keep all native search/filter controls and query parameters intact.
    const filterForm = document.querySelector('#changelist-search');
    if (filterForm) {
      const disclosure = document.createElement('details');
      disclosure.className = 'zad-filter-disclosure';
      const summary = document.createElement('summary');
      summary.textContent = 'جستجو و فیلترها';
      disclosure.append(summary);
      filterForm.before(disclosure);
      disclosure.append(filterForm);
      const listMobile = window.matchMedia('(max-width: 760px)');
      disclosure.open = !listMobile.matches || !!window.location.search;
      listMobile.addEventListener('change', () => { disclosure.open = !listMobile.matches || !!window.location.search; });
      const search = filterForm.querySelector('#searchbar');
      if (search) { search.setAttribute('aria-label', 'جستجو در این فهرست'); if (!search.placeholder.trim()) search.placeholder = 'نام یا کد را جستجو کنید'; }
    }

    const productModels = ['flower', 'samedayflower', 'weddingproduct', 'bakeryitem', 'giftitem', 'product'];
    const table = document.querySelector('#result_list');
    if (table && productModels.some(model => document.body.classList.contains(`model-${model}`))) {
      table.classList.add('zad-product-cards');
      const headers = [...table.querySelectorAll('thead th')];
      table.querySelectorAll('tbody tr').forEach(row => {
        [...row.children].forEach((cell, i) => { cell.dataset.label = headers[i]?.textContent.trim() || ''; });
      });
      const sort = document.createElement('details');
      sort.className = 'zad-mobile-sort';
      const summary = document.createElement('summary');
      summary.textContent = 'مرتب‌سازی و انتخاب گروهی';
      sort.append(summary);
      const links = document.createElement('div');
      headers.forEach(header => {
        const link = header.querySelector('.text a');
        if (link && link.textContent.trim()) links.append(link.cloneNode(true));
      });
      const all = table.querySelector('#action-toggle');
      if (all) {
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'zad-button zad-button--quiet';
        button.textContent = 'انتخاب / لغو انتخاب این صفحه';
        button.addEventListener('click', () => all.click());
        links.append(button);
      }
      sort.append(links); table.parentNode.before(sort);
    }

    const pageSelect = document.querySelector('[data-zad-slots]');
    const slotSelect = document.querySelector('#id_section_key');
    if (pageSelect && slotSelect) {
      const registry = JSON.parse(pageSelect.dataset.zadSlots);
      const originalPage = pageSelect.value, originalKey = slotSelect.value;
      const info = document.createElement('p'); info.className = 'zad-slot-info';
      info.setAttribute('role', 'status'); slotSelect.after(info);
      const labels = {kicker: 'عنوان کوتاه', title: 'عنوان', body: 'متن'};
      const explain = () => {
        const slot = registry[pageSelect.value]?.[slotSelect.value];
        info.textContent = slot ? `فیلدهای متصل به سایت: ${slot.fields.map(field => labels[field] || field).join('، ')}` : 'صفحه و بخش متصل را انتخاب کنید؛ رکوردهای قدیمی بدون حذف حفظ می‌شوند.';
      };
      const updateSlots = () => {
        const selected = slotSelect.value;
        const slots = registry[pageSelect.value] || {};
        slotSelect.replaceChildren(new Option('بخش را انتخاب کنید', ''));
        Object.entries(slots).forEach(([key, slot]) => slotSelect.add(new Option(slot.label, key)));
        if (pageSelect.value === originalPage && originalKey && !slots[originalKey]) {
          slotSelect.add(new Option('جایگاه قدیمی؛ حفظ اطلاعات', originalKey));
        }
        slotSelect.value = [...slotSelect.options].some(option => option.value === selected) ? selected : '';
        if (window.jQuery) window.jQuery(slotSelect).trigger('change.select2');
        explain();
      };
      pageSelect.addEventListener('change', updateSlots);
      slotSelect.addEventListener('change', explain);
      if (window.jQuery) {
        window.jQuery(pageSelect).on('change.zadSlots', updateSlots);
        window.jQuery(slotSelect).on('change.zadSlots', explain);
      }
      updateSlots();
    }

    const form = document.querySelector('.change-form #content-main > form');
    if (form) {
      let dirty = false;
      const statuses = form.querySelectorAll('.zad-save-status');
      const markDirty = () => { dirty = true; statuses.forEach(node => { node.textContent = 'تغییرات هنوز ذخیره نشده‌اند'; }); };
      form.addEventListener('input', markDirty);
      form.addEventListener('change', markDirty);
      form.addEventListener('submit', () => { dirty = false; });
      window.addEventListener('beforeunload', event => {
        if (dirty) { event.preventDefault(); event.returnValue = ''; }
      });
      // A server validation error may be in an inactive Jazzmin tab.
      const firstError = form.querySelector('.errorlist, .invalid-feedback');
      const pane = firstError?.closest('.tab-pane');
      if (pane && pane.id && window.bootstrap?.Tab) {
        const tab = [...form.querySelectorAll('[data-bs-toggle="tab"]')].find(node => node.getAttribute('href') === `#${pane.id}` || node.dataset.bsTarget === `#${pane.id}`);
        if (tab) window.bootstrap.Tab.getOrCreateInstance(tab).show();
      }
    }

    const prepareUploads = (root) => {
      root.querySelectorAll('input[type="file"]').forEach(input => {
        if (input.dataset.zadPreview) return;
        input.dataset.zadPreview = 'true';
        input.addEventListener('change', () => {
          input.parentElement.querySelectorAll('.zad-upload-preview, .zad-upload-note').forEach(node => node.remove());
          const file = input.files?.[0];
          if (!file) return;
          const note = document.createElement('small'); note.className = 'zad-upload-note';
          note.textContent = `${file.name} — پیش‌نمایش فایل انتخاب‌شده؛ برای ثبت، ذخیره کنید.`;
          input.after(note);
          if (!['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(file.type) || file.size > 20 * 1024 * 1024) return;
          const img = document.createElement('img'); img.className = 'zad-upload-preview'; img.alt = 'پیش‌نمایش تصویر انتخاب‌شده';
          const reader = new FileReader();
          reader.addEventListener('load', () => { if (input.files?.[0] === file) { img.src = reader.result; note.after(img); } });
          reader.readAsDataURL(file);
        });
      });
    };
    prepareUploads(document);
    document.addEventListener('formset:added', event => prepareUploads(event.target));
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, {once: true});
  else ready();
})();
