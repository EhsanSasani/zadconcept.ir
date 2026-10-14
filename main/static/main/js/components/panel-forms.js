/* Shared progressive enhancement for manager, sales and procurement only. */
(() => {
  const normalize = value => value.replace(/[۰-۹]/g, c => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(c)))
    .replace(/[٠-٩]/g, c => String('٠١٢٣٤٥٦٧٨٩'.indexOf(c))).replace(/[,٬\s]/g, '');
  document.querySelectorAll('[data-money],[data-price-input]').forEach(input => {
    const format = () => {
      const raw = normalize(input.value);
      if (!/^\d*$/.test(raw)) return;
      const caret = input.selectionStart;
      const left = normalize(input.value.slice(0, caret ?? input.value.length)).length;
      input.value = raw.replace(/\B(?=(\d{3})+(?!\d))/g, '٬');
      if (document.activeElement === input && caret !== null) {
        let position = 0, digits = 0;
        while (position < input.value.length && digits < left) {
          if (/\d/.test(input.value[position])) digits++;
          position++;
        }
        input.setSelectionRange(position, position);
      }
    };
    format();
    input.addEventListener('input', format);
  });
  document.querySelectorAll('[data-receipt-input]').forEach(input => {
    const preview = input.closest('form').querySelector('[data-receipt-preview]');
    const hint = input.closest('form').querySelector('[data-receipt-hint]');
    let url;
    input.addEventListener('change', () => {
      if (url) URL.revokeObjectURL(url);
      preview.hidden = true;
      const file = input.files?.[0];
      if (!file) { hint.textContent = ''; return; }
      hint.textContent = file.name;
      if (file.type.startsWith('image/')) {
        url = URL.createObjectURL(file);
        preview.src = url;
        preview.hidden = false;
      }
    });
    preview.addEventListener('error', () => {
      preview.hidden = true;
      hint.textContent = 'پیش‌نمایش این فرمت در مرورگر ممکن نیست؛ تصویر هنگام ثبت بررسی می‌شود.';
    });
  });
  document.querySelectorAll('form[data-panel-submit]').forEach(form => {
    form.addEventListener('submit', event => {
      if (form.dataset.submitting === 'true') { event.preventDefault(); return; }
      if (!form.checkValidity()) return;
      form.dataset.submitting = 'true';
      form.setAttribute('aria-busy', 'true');
      // Preserve the clicked button's value for submit-and-continue actions.
      form.querySelectorAll('button[type="submit"]').forEach(button => {
        button.setAttribute('aria-disabled', 'true');
        button.textContent = 'در حال ثبت…';
      });
    });
  });
})();
