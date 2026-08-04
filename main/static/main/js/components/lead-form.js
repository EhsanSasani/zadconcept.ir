function initLeadForm(form) {
  const leadType = form.querySelector('[name="lead_type"]');
  const deliveryWindow = form.querySelector('[name="delivery_window"]');
  const eventRow = form.querySelector("[data-lead-event-field]");
  const dateRow = form.querySelector("[data-lead-date-field]");
  const eventInput = eventRow?.querySelector("input, select, textarea");
  const dateInput = dateRow?.querySelector("input, select, textarea");
  if (!leadType || !deliveryWindow) return;

  function refresh() {
    const needsEvent = leadType.value === "event";
    const needsDate = deliveryWindow.value === "pick_date";
    const eventHasError = Boolean(
      eventRow?.querySelector('.errorlist, [aria-invalid="true"]'),
    );
    const dateHasError = Boolean(
      dateRow?.querySelector('.errorlist, [aria-invalid="true"]'),
    );
    if (eventRow) eventRow.hidden = !needsEvent && !eventHasError;
    if (dateRow) dateRow.hidden = !needsDate && !dateHasError;
    if (eventInput) {
      eventInput.required = needsEvent;
      eventInput.setAttribute("aria-required", String(needsEvent));
    }
    if (dateInput) {
      dateInput.required = needsDate;
      dateInput.setAttribute("aria-required", String(needsDate));
    }
  }

  leadType.addEventListener("change", refresh);
  deliveryWindow.addEventListener("change", refresh);
  refresh();
}

export function initLeadForms() {
  document.querySelectorAll("form[data-lead-form]").forEach(initLeadForm);
  const errorSummary = document.querySelector("[data-form-error-summary]");
  if (errorSummary) window.requestAnimationFrame(() => errorSummary.focus());
}
