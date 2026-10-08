/* Progressive enhancement: every ledger form also submits without JavaScript. */
(() => {
  'use strict';
  const form = document.querySelector('[data-proc-entry]');
  if (!form) return;
  const dataNode = document.getElementById('proc-material-data');
  let materials;
  try { materials = new Map(JSON.parse(dataNode.textContent).map(item => [String(item.id), item])); }
  catch (_) { return; }
  const container = form.querySelector('[data-proc-lines]');
  const template = form.querySelector('[data-proc-empty]');
  const add = form.querySelector('[data-proc-add]');
  const management = form.querySelector('[name="lines-TOTAL_FORMS"]');
  const maxForms = Math.min(50, Number(form.querySelector('[name="lines-MAX_NUM_FORMS"]')?.value) || 50);
  const announcer = document.querySelector('[data-proc-announcer]');
  const numberFormat = new Intl.NumberFormat('fa-IR', {maximumFractionDigits: 3});
  const moneyFormat = new Intl.NumberFormat('fa-IR', {maximumFractionDigits: 0});
  const digits = value => String(value ?? '').replace(/[۰-۹]/g, c => String(c.charCodeAt(0) - 1776)).replace(/[٠-٩]/g, c => String(c.charCodeAt(0) - 1632));
  const normalize = (value, money = false) => {
    let normalized = digits(value).replace(/[,٬\s]/g, '').replace(/٫/g, '.');
    if (money && /^\d{1,3}(?:\.\d{3})+$/.test(normalized)) normalized = normalized.replace(/\./g, '');
    return normalized;
  };
  const parse = (value, money = false) => /^\d+(?:\.\d+)?$/.test(normalize(value, money)) ? Number(normalize(value, money)) : NaN;
  // Match whole-toman server rounding without floating-point errors on large invoices.
  const lineAmount = (quantity, price) => {
    const qty = normalize(quantity);
    const money = normalize(price, true);
    if (!/^\d+(?:\.\d{1,3})?$/.test(qty) || !/^\d+$/.test(money)) return null;
    const [whole, fraction = ''] = qty.split('.');
    const thousandths = BigInt(whole + fraction.padEnd(3, '0'));
    if (thousandths <= 0n) return null;
    return (thousandths * BigInt(money) + 500n) / 1000n;
  };
  const field = (row, name) => row.querySelector(`[name$="-${name}"]`);
  const allRows = () => [...container.querySelectorAll('[data-proc-line]')];
  const visibleRows = () => allRows().filter(row => !row.hidden);
  const say = message => { if (announcer) announcer.textContent = message; };
  const materialFor = row => materials.get(field(row, 'material').value);

  function updateLabels(row) {
    const item = materialFor(row);
    const mode = field(row, 'unit_mode');
    for (const option of mode.options) option.textContent = item ? (option.value === 'base' ? item.base_unit : item.purchase_unit) : (option.value === 'base' ? 'پایه' : 'خرید');
    const pack = mode.value === 'purchase';
    const factorWrapper = row.querySelector('[data-proc-factor-wrap]');
    // Keep invalid inputs visible so server validation is always actionable.
    factorWrapper.hidden = (!pack || (form.dataset.kind === 'purchase' && !item)) && !factorWrapper.querySelector('.errorlist');
    row.querySelector('[data-proc-factor-label]').textContent = item ? `تعداد ${item.base_unit} در هر ${item.purchase_unit}` : 'تعداد در هر واحد خرید';
    row.querySelector('[data-proc-factor-help]').textContent = item ? `خالی بماند: ${numberFormat.format(Number(item.units_per_purchase))} ${item.base_unit}` : 'مثلاً تعداد شاخه در هر بسته';
    const priceLabel = row.querySelector('[data-proc-price-label]');
    if (priceLabel) priceLabel.textContent = `قیمت هر ${item ? (pack ? item.purchase_unit : item.base_unit) : 'واحد'} · تومان`;
  }

  function setMaterialDefaults(row) {
    const item = materialFor(row);
    if (!item) { updateLabels(row); recalculate(); return; }
    const pack = field(row, 'unit_mode').value === 'purchase';
    const factor = Number(item.units_per_purchase);
    field(row, 'conversion_factor').value = pack ? String(factor) : '1';
    const materialVersion = field(row, 'material_version');
    if (materialVersion) materialVersion.value = item.version || '';
    row.dataset.packFactor = String(factor);
    const price = field(row, 'unit_price');
    if (price) price.value = String(Math.round(Number(item.default_unit_price) / (pack ? 1 : factor)));
    updateLabels(row);
    recalculate();
  }

  function switchUnit(row) {
    const item = materialFor(row);
    const factorField = field(row, 'conversion_factor');
    const pack = field(row, 'unit_mode').value === 'purchase';
    const previousFactor = parse(factorField.value) || Number(item?.units_per_purchase) || 1;
    const packFactor = pack ? (Number(row.dataset.packFactor) || Number(item?.units_per_purchase) || 1) : previousFactor;
    if (!pack) row.dataset.packFactor = String(previousFactor);
    const price = field(row, 'unit_price');
    if (price && Number.isFinite(parse(price.value, true))) price.value = String(Math.round(parse(price.value, true) * (pack ? packFactor : 1 / packFactor)));
    factorField.value = pack ? String(packFactor) : '1';
    updateLabels(row);
    recalculate();
  }

  function recalculate() {
    let total = 0n;
    let validTotal = true;
    let entered = 0;
    visibleRows().forEach((row, index) => {
      row.querySelector('[data-proc-row-number]').textContent = numberFormat.format(index + 1);
      const item = materialFor(row);
      if (item) entered += 1;
      const quantity = parse(field(row, 'quantity').value);
      const pack = field(row, 'unit_mode').value === 'purchase';
      const factor = pack ? (field(row, 'conversion_factor').value.trim() === '' ? Number(item?.units_per_purchase) : parse(field(row, 'conversion_factor').value)) : 1;
      const conversion = row.querySelector('[data-proc-conversion-preview]');
      if (form.dataset.kind === 'waste') row.querySelector('.proc-line-bottom').hidden = !(item && quantity > 0 && factor > 0);
      conversion.textContent = item && quantity > 0 && factor > 0 ? `معادل ${numberFormat.format(quantity * factor)} ${item.base_unit}` : 'مقدار بر اساس واحد انتخاب‌شده ثبت می‌شود.';
      const price = field(row, 'unit_price');
      const lineTotal = row.querySelector('[data-proc-line-total]');
      if (price) {
        const subtotal = lineAmount(field(row, 'quantity').value, price.value);
        const valid = item && subtotal !== null;
        if (lineTotal) lineTotal.textContent = valid ? moneyFormat.format(subtotal) : '—';
        if (valid) total += subtotal;
        else if (item) validTotal = false;
      }
    });
    const totalNode = form.querySelector('[data-proc-total]');
    if (totalNode) totalNode.textContent = validTotal && entered ? moneyFormat.format(total) : '—';
    const countNode = form.querySelector('[data-proc-line-count]');
    if (countNode) countNode.textContent = entered ? `${numberFormat.format(entered)} ردیف کالا` : '';
    add.disabled = visibleRows().length >= maxForms;
  }

  function prepare(row) {
    const deleteInput = field(row, 'DELETE');
    row.querySelector('.proc-delete-check').hidden = true;
    row.querySelector('[data-proc-remove]').hidden = false;
    if (deleteInput.checked) row.hidden = true;
    const materialVersion = field(row, 'material_version');
    const item = materialFor(row);
    if (materialVersion && item && !materialVersion.value && !form.querySelector('[data-proc-errors]')) materialVersion.value = item.version || '';
    updateLabels(row);
  }

  container.addEventListener('change', event => {
    const row = event.target.closest('[data-proc-line]');
    if (!row) return;
    if (event.target === field(row, 'material')) setMaterialDefaults(row);
    else if (event.target === field(row, 'unit_mode')) switchUnit(row);
    else recalculate();
  });
  container.addEventListener('input', recalculate);
  // Enter continues the batch instead of saving it before all rows are entered.
  container.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || event.isComposing) return;
    const row = event.target.closest('[data-proc-line]');
    const lastField = form.dataset.kind === 'purchase' ? 'unit_price' : 'quantity';
    if (!row || event.target !== field(row, lastField)) return;
    event.preventDefault();
    if (!materialFor(row)) { field(row, 'material').focus(); return; }
    if (!(parse(field(row, 'quantity').value) > 0)) { field(row, 'quantity').focus(); return; }
    if (lastField === 'unit_price' && lineAmount(field(row, 'quantity').value, event.target.value) === null) return;
    const next = visibleRows()[visibleRows().indexOf(row) + 1];
    if (next) field(next, 'material').focus();
    else if (!add.disabled) add.click();
  });
  container.addEventListener('click', event => {
    const button = event.target.closest('[data-proc-remove]');
    if (!button) return;
    const row = button.closest('[data-proc-line]');
    field(row, 'DELETE').checked = true;
    row.hidden = true;
    recalculate();
    const next = visibleRows().at(-1);
    (next ? field(next, 'material') : add).focus();
    say('ردیف حذف شد.');
  });
  add.addEventListener('click', () => {
    // Reuse a removed form, so repeated add/remove never exhausts Django's cap.
    let row = allRows().find(item => item.hidden);
    if (row) {
      const prefix = field(row, 'material').name.replace(/-material$/, '');
      const holder = document.createElement('template');
      holder.innerHTML = template.innerHTML.replaceAll('lines-__prefix__', prefix);
      const replacement = holder.content.firstElementChild;
      row.replaceWith(replacement);
      row = replacement;
    } else {
      const index = Number(management.value);
      if (index >= maxForms) return;
      const holder = document.createElement('template');
      holder.innerHTML = template.innerHTML.replaceAll('__prefix__', String(index));
      row = holder.content.firstElementChild;
      container.append(row);
      management.value = String(index + 1);
    }
    prepare(row);
    recalculate();
    field(row, 'material').focus();
    say('ردیف جدید اضافه شد.');
  });
  allRows().forEach(prepare);
  add.hidden = false;
  recalculate();
  // Start with one row on a pristine form; preserve every submitted row/error.
  if (!form.querySelector('[data-proc-errors]') && allRows().every(row => !field(row, 'material').value)) {
    allRows().slice(1).forEach(row => { field(row, 'DELETE').checked = true; row.hidden = true; });
    recalculate();
  }
  const errors = form.querySelector('[data-proc-errors]');
  if (errors) errors.focus({preventScroll: false});
  let refreshing = false;
  window.addEventListener('focus', async () => {
    if (refreshing || !form.dataset.materialsUrl) return;
    refreshing = true;
    try {
      const response = await fetch(form.dataset.materialsUrl, {credentials: 'same-origin', headers: {'Accept': 'application/json'}, cache: 'no-store'});
      if (!response.ok) return;
      const payload = await response.json();
      if (!Array.isArray(payload.materials)) return;
      const fresh = new Map(payload.materials.map(item => [String(item.id), item]));
      const added = [...fresh.keys()].some(key => !materials.has(key));
      const updateOptions = select => {
        const selected = select.value;
        const oldLabel = select.selectedOptions[0]?.textContent || 'کالای قبلی';
        select.replaceChildren(new Option('انتخاب کالا', ''));
        for (const item of fresh.values()) select.add(new Option(item.name, String(item.id)));
        // Retain revoked choices visibly; the server then explains why they cannot submit.
        if (selected && !fresh.has(selected)) select.add(new Option(`${oldLabel.replace(/ · غیرفعال$/, '')} · غیرفعال`, selected));
        select.value = selected;
      };
      allRows().forEach(row => updateOptions(field(row, 'material')));
      updateOptions(template.content.querySelector('[name$="-material"]'));
      materials = fresh;
      allRows().forEach(updateLabels);
      recalculate();
      if (fresh.size) document.querySelector('[data-proc-no-materials]')?.remove();
      if (added) say('فهرست کالاها به‌روز شد. کالای جدید آمادهٔ انتخاب است.');
    } catch (_) { /* Keep the form and entered data available during connection failures. */ }
    finally { refreshing = false; }
  });
})();
