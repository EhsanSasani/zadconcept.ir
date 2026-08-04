function initLeadForm(form) {
  const leadType = form.querySelector('[name="lead_type"]');
  const deliveryWindow = form.querySelector('[name="delivery_window"]');
  const eventRow = form.querySelector("[data-lead-event-field]");
  const dateRow = form.querySelector("[data-lead-date-field]");
  if (!leadType || !deliveryWindow) return;

  function refresh() {
    if (eventRow) eventRow.hidden = leadType.value !== "event";
    if (dateRow) dateRow.hidden = deliveryWindow.value !== "pick_date";
  }

  leadType.addEventListener("change", refresh);
  deliveryWindow.addEventListener("change", refresh);
  refresh();
}

export function initLeadForms() {
  document.querySelectorAll("form[data-lead-form]").forEach(initLeadForm);
}
