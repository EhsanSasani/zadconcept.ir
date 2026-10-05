(() => {
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    let busy = false;
    form.addEventListener('submit', event => {
      if (busy || !form.reportValidity() || !window.confirm(form.dataset.confirm)) {
        event.preventDefault(); return;
      }
      busy = true;
      form.querySelectorAll('button[type="submit"],button:not([type])').forEach(button => {
        button.disabled = true; button.textContent = 'در حال ثبت…';
      });
    });
    window.addEventListener('pageshow', event => { if(event.persisted) location.reload(); });
  });
  document.querySelector('[data-open-action]')?.addEventListener('click', () => {
    const action = document.querySelector('#sale-actions details');
    if(action) action.open = true;
  });
  const input = document.querySelector('[data-preview-input]');
  const preview = document.querySelector('[data-preview]');
  let url;
  input?.addEventListener('change', () => {
    if(url) URL.revokeObjectURL(url);
    preview.hidden = true;
    const file = input.files[0];
    if(file?.type.startsWith('image/')) {
      url=URL.createObjectURL(file); preview.src=url; preview.hidden=false;
    }
  });
  preview?.addEventListener('error',()=>{preview.hidden=true;});
  // Group thousands without moving the caret while the operator types.
  const price = document.querySelector('[data-price-input]');
  const normalize = value => value.replace(/[۰-۹]/g,c=>String('۰۱۲۳۴۵۶۷۸۹'.indexOf(c))).replace(/[٠-٩]/g,c=>String('٠١٢٣٤٥٦٧٨٩'.indexOf(c))).replace(/[,٬\s]/g,'');
  const format = () => { const raw=normalize(price.value); if(/^\d+$/.test(raw)) price.value=raw.replace(/\B(?=(\d{3})+(?!\d))/g,','); };
  if(price){format();price.addEventListener('blur',format);}
})();
