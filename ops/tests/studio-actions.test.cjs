const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../main/static/main/js/pages/studio.js'), 'utf8');

function fixture({ dialogAvailable = true, fallbackConfirmed = true, delayedClose = false } = {}) {
  const events = {};
  let document;
  function node(textContent = '') {
    const handlers = {};
    return {
      textContent, disabled: false,
      addEventListener(type, handler) { (handlers[type] ??= []).push(handler); },
      dispatch(type, extra = {}) {
        const event = { target: this, currentTarget: this, ...extra };
        for (const handler of handlers[type] ?? []) handler(event);
      },
      focus() { document.activeElement = this; },
    };
  }
  const title = node('ثبت وضعیت محصول');
  const description = node();
  const help = node();
  const confirm = node('تأیید و ثبت');
  const cancel = node('انصراف');
  const announcer = node();
  const dialog = Object.assign(node(), {
    open: false, opened: 0,
    querySelector(selector) {
      return { '#status-title': title, '[data-status-description]': description,
        'p.muted': help, '[data-close-dialog]': cancel }[selector] ?? null;
    },
    showModal() { this.open = true; this.opened++; },
    close() { this.open = false; if (!delayedClose) this.dispatch('close'); },
  });
  cancel.closest = selector => ({ '[data-close-dialog]': cancel, dialog }[selector] ?? null);
  document = {
    body: { classList: { toggle() {} } },
    querySelector(selector) {
      return { '#status-dialog': dialogAvailable ? dialog : null,
        '[data-confirm-status]': dialogAvailable ? confirm : null,
        '[data-announcer]': announcer }[selector] ?? null;
    },
    querySelectorAll(selector) { return selector === 'dialog' && dialogAvailable ? [dialog] : []; },
    addEventListener(type, callback) { (events[type] ??= []).push(callback); },
  };
  const submissions = [];
  const confirmations = [];
  const window = {
    matchMedia() { return { matches: false, addEventListener() {} }; },
    addEventListener() {},
    confirm(text) { confirmations.push(text); return fallbackConfirmed; },
  };
  vm.runInNewContext(source, { document, window,
    HTMLFormElement: { prototype: { submit() { submissions.push(this); } } } });
  function form(kind, { reason = 'ثبت اشتباه', status = 'SOLD', factor = 'A-123' } = {}) {
    const reasonInput = { value: reason };
    const select = { selectedOptions: [{ value: status, textContent: 'فروخته شد' }] };
    const button = node();
    return {
      isConnected: true, dataset: { factor }, button, reasonInput, select,
      matches(selector) { return selector.split(',').some(part => part === `.${kind}`); },
      querySelector(selector) {
        return { 'input[name=reason]': kind === 'product-delete-form' ? reasonInput : null,
          'select[name=status]': kind === 'status-form' ? select : null }[selector] ?? null;
      },
      querySelectorAll(selector) { return selector === 'button[type=submit]' ? [button] : []; },
      reportValidity() { return kind === 'product-delete-form' ? Boolean(reasonInput.value) : Boolean(status); },
    };
  }
  function fire(type, target) {
    const event = { target, prevented: false, preventDefault() { this.prevented = true; } };
    for (const handler of events[type] ?? []) handler(event);
    return event;
  }
  return { form, fire, dialog, title, description, help, confirm, cancel,
    announcer, document, submissions, confirmations };
}

test('deletion confirms without a status select, safely displays text and focuses cancellation', () => {
  const f = fixture();
  const form = f.form('product-delete-form', { factor: '<script>alert(1)</script>', reason: '<img src=x>' });
  assert.equal(f.fire('submit', form).prevented, true);
  assert.equal(f.dialog.open, true);
  assert.match(f.description.textContent, /<script>alert\(1\)<\/script>/);
  assert.match(f.description.textContent, /<img src=x>/);
  assert.match(f.title.textContent, /حذف مدیریتی/);
  assert.match(f.help.textContent, /سابقهٔ مدیریتی محفوظ/);
  assert.equal(f.document.activeElement, f.cancel);
  assert.equal(f.submissions.length, 0);
});

test('confirmation and repeated submit events send a deletion only once', () => {
  const f = fixture();
  const form = f.form('product-delete-form');
  f.fire('submit', form);
  f.fire('submit', form);
  f.confirm.dispatch('click');
  f.confirm.dispatch('click');
  f.fire('submit', form);
  assert.deepEqual(f.submissions, [form]);
  assert.equal(f.dialog.opened, 1);
  assert.equal(f.confirm.disabled, true);
  assert.equal(form.button.disabled, true);
});

test('cancellation clears deletion so the existing status action can be confirmed', () => {
  const f = fixture();
  const deleted = f.form('product-delete-form');
  f.fire('submit', deleted);
  f.fire('click', f.cancel);
  assert.equal(f.dialog.open, false);
  assert.equal(f.submissions.length, 0);
  const status = f.form('status-form');
  f.fire('submit', status);
  assert.equal(f.title.textContent, 'ثبت وضعیت محصول');
  assert.match(f.description.textContent, /فروخته شد/);
  assert.equal(f.help.textContent, 'این محصول از فهرست موجودها خارج می‌شود.');
  f.confirm.dispatch('click');
  assert.deepEqual(f.submissions, [status]);
});

test('native dialog dismissal clears pending deletion before reopening', () => {
  const f = fixture();
  const first = f.form('product-delete-form', { factor: 'FIRST' });
  const second = f.form('product-delete-form', { factor: 'SECOND' });
  f.fire('submit', first);
  f.dialog.close();
  f.confirm.dispatch('click');
  assert.equal(f.submissions.length, 0);
  f.fire('submit', second);
  f.confirm.dispatch('click');
  assert.deepEqual(f.submissions, [second]);
});

test('a queued previous close cannot clear the new confirmation', () => {
  const f = fixture({ delayedClose: true });
  const first = f.form('product-delete-form', { factor: 'FIRST' });
  const second = f.form('product-delete-form', { factor: 'SECOND' });
  f.fire('submit', first);
  f.dialog.close();
  f.confirm.dispatch('click');
  assert.equal(f.submissions.length, 0);
  f.fire('submit', second);
  f.dialog.dispatch('close');
  f.confirm.dispatch('click');
  assert.deepEqual(f.submissions, [second]);
});

test('blank deletion reason and unselected status never open a confirmation or submit', () => {
  const f = fixture();
  const deletion = f.form('product-delete-form', { reason: '  \t ' });
  const status = f.form('status-form', { status: '' });
  assert.equal(f.fire('submit', deletion).prevented, true);
  assert.equal(f.fire('submit', status).prevented, true);
  assert.equal(deletion.reasonInput.value, '');
  assert.equal(f.dialog.opened, 0);
  assert.equal(f.submissions.length, 0);
});

test('a table replaced by sorting cannot submit its detached pending form', () => {
  const f = fixture();
  const form = f.form('product-delete-form');
  f.fire('submit', form);
  form.isConnected = false;
  f.confirm.dispatch('click');
  assert.equal(f.submissions.length, 0);
  assert.equal(f.dialog.open, false);
  assert.ok(f.announcer.textContent);
});

test('confirmation rechecks validation if data becomes invalid while modal is open', () => {
  const f = fixture();
  const form = f.form('product-delete-form');
  f.fire('submit', form);
  form.reasonInput.value = '';
  f.confirm.dispatch('click');
  assert.equal(f.submissions.length, 0);
  assert.equal(form.button.disabled, false);
  assert.equal(f.confirm.disabled, false);
});

for (const confirmed of [true, false]) {
  test(`without dialog support native confirmation stays safe (confirmed=${confirmed})`, () => {
    const f = fixture({ dialogAvailable: false, fallbackConfirmed: confirmed });
    const form = f.form('product-delete-form');
    assert.equal(f.fire('submit', form).prevented, true);
    if (confirmed) f.fire('submit', form);
    assert.equal(f.confirmations.length, 1);
    assert.equal(f.submissions.length, confirmed ? 1 : 0);
  });
}
