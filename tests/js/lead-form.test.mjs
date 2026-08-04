import test from "node:test";
import assert from "node:assert/strict";

import { initLeadForms } from "../../main/static/main/js/components/lead-form.js";
import { installDom } from "./dom-helpers.mjs";

test("lead form synchronizes conditional visibility and required state", () => {
  const cleanup = installDom(`
    <div data-form-error-summary tabindex="-1"></div>
    <form data-lead-form>
      <select name="lead_type"><option value="flower" selected>Flower</option><option value="event">Event</option></select>
      <select name="delivery_window"><option value="today" selected>Today</option><option value="pick_date">Date</option></select>
      <label data-lead-event-field><input name="event_location"></label>
      <label data-lead-date-field><input name="preferred_date"></label>
    </form>
  `);
  initLeadForms();

  const leadType = document.querySelector('[name="lead_type"]');
  const deliveryWindow = document.querySelector('[name="delivery_window"]');
  const eventRow = document.querySelector("[data-lead-event-field]");
  const dateRow = document.querySelector("[data-lead-date-field]");
  const eventInput = eventRow.querySelector("input");
  const dateInput = dateRow.querySelector("input");

  assert.equal(eventRow.hidden, true);
  assert.equal(dateRow.hidden, true);
  assert.equal(eventInput.required, false);
  assert.equal(dateInput.required, false);
  assert.equal(document.activeElement, document.querySelector("[data-form-error-summary]"));

  leadType.value = "event";
  deliveryWindow.value = "pick_date";
  leadType.dispatchEvent(new window.Event("change", { bubbles: true }));
  deliveryWindow.dispatchEvent(new window.Event("change", { bubbles: true }));

  assert.equal(eventRow.hidden, false);
  assert.equal(dateRow.hidden, false);
  assert.equal(eventInput.required, true);
  assert.equal(dateInput.required, true);
  assert.equal(eventInput.getAttribute("aria-required"), "true");
  assert.equal(dateInput.getAttribute("aria-required"), "true");
  cleanup();
});

test("lead form keeps an invalid conditional field visible for repair", () => {
  const cleanup = installDom(`
    <form data-lead-form>
      <select name="lead_type"><option value="flower" selected>Flower</option></select>
      <select name="delivery_window"><option value="today" selected>Today</option></select>
      <div data-lead-event-field><input name="event_location"></div>
      <div data-lead-date-field>
        <input name="preferred_date" aria-invalid="true">
        <ul class="errorlist"><li>Invalid date</li></ul>
      </div>
    </form>
  `);
  initLeadForms();

  const dateRow = document.querySelector("[data-lead-date-field]");
  const dateInput = dateRow.querySelector("input");
  assert.equal(dateRow.hidden, false);
  assert.equal(dateInput.required, false);
  assert.equal(dateInput.getAttribute("aria-required"), "false");
  cleanup();
});
