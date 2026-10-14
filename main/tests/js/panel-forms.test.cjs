const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const source = readFileSync('main/static/main/js/components/panel-forms.js', 'utf8');

function inputHarness(value, caret = value.length) {
  const events = {};
  const input = {value, selectionStart:caret,
    addEventListener:(name, listener) => {events[name] = listener;},
    setSelectionRange:(start) => {input.selectionStart = start;}};
  const document = {activeElement:input,
    querySelectorAll:(selector) => selector === '[data-money],[data-price-input]' ? [input] : []};
  vm.runInNewContext(source, {document});
  return {input, events};
}

test('money formatting preserves all 18 digits without numeric rounding', () => {
  const {input} = inputHarness('۹۹۹۹۹۹۹۹۹۹۹۹۹۹۹۹۹۹');
  assert.equal(input.value,'999٬999٬999٬999٬999٬999');
  assert.equal(input.selectionStart,input.value.length);
});

test('typing in the middle preserves the caret after the same number of digits', () => {
  const {input,events} = inputHarness('1234567');
  input.value='1٬2934٬567';
  input.selectionStart=4;
  events.input();
  assert.equal(input.value,'12٬934٬567');
  assert.equal(input.selectionStart,4);
  assert.equal(input.value.slice(0,input.selectionStart).replace(/٬/g,''),'129');
});

test('invalid fractional money is left visible for server validation', () => {
  const {input} = inputHarness('۱۲٫۵');
  assert.equal(input.value,'۱۲٫۵');
});
