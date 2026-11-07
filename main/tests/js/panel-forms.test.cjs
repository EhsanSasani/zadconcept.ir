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

function invalidFormHarness({interacted=false,summaryOnly=false,hiddenFirst=false}={}) {
  const docEvents={},winEvents={};const order=[];
  const details={tagName:'DETAILS',open:false,parentElement:null};
  const field={id:'bad-value',type:'text',disabled:false,parentElement:details,
    getClientRects:()=>details.open?[{}]:[],focus(){order.push('field');}};
  const hidden={type:'hidden',disabled:false};
  const summary={textContent:'Server error',tabIndex:0,parentElement:null,focus(){order.push('summary');}};
  const document={querySelectorAll(selector){
    if(selector==='[aria-invalid="true"]')return summaryOnly?[]:hiddenFirst?[hidden,field]:[field];
    if(selector==='form .errorlist, form [role="alert"]')return [summary];
    return [];
  },addEventListener:(name,fn)=>(docEvents[name]??=[]).push(fn)};
  const window={addEventListener:(name,fn)=>(winEvents[name]??=[]).push(fn)};
  vm.runInNewContext(source,{document,window,requestAnimationFrame:fn=>fn()});
  if(interacted)for(const fn of docEvents.pointerdown||[])fn();
  for(const fn of winEvents.pageshow||[])fn({persisted:false});
  return {details,order,summary};
}
test('server validation reveals the closed section and focuses the invalid field after autofocus',()=>{
  const f=invalidFormHarness();assert.equal(f.details.open,true);assert.deepEqual(f.order,['field']);
});
test('hidden invalid metadata is skipped in favor of an actionable field',()=>{
  assert.deepEqual(invalidFormHarness({hiddenFirst:true}).order,['field']);
});
test('non-field errors receive focus when there is no actionable invalid input',()=>{
  const f=invalidFormHarness({summaryOnly:true});assert.deepEqual(f.order,['summary']);assert.equal(f.summary.tabIndex,-1);
});
test('late error focus never steals an intentional user interaction',()=>{
  assert.deepEqual(invalidFormHarness({interacted:true}).order,[]);
});
