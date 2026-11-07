const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('main/static/main/js/pages/team.js','utf8');

async function fixture({price='',draft}={}){
  const nodes=new Map();
  function node(){
    const handlers={};
    return {value:'',hidden:false,disabled:false,files:[],open:false,textContent:'',dataset:{},
      classList:{add(){},remove(){},toggle(){}},
      addEventListener:(name,fn)=>(handlers[name]??=[]).push(fn),
      emit:(name,event={})=>{for(const fn of handlers[name]||[])fn(event);},
      setAttribute(){},removeAttribute(){},querySelectorAll:()=>[],
      setCustomValidity(value){this.validationMessage=value;},
      setSelectionRange(start,end,direction){this.selectionStart=start;this.selectionEnd=end;this.selectionDirection=direction;},
      focus(){},replaceChildren(){}};
  }
  const get=selector=>{if(!nodes.has(selector))nodes.set(selector,node());return nodes.get(selector);};
  const form=get('[data-product-form]');form.querySelector=get;
  form.elements=Object.fromEntries(['submission_key','florist','production_type','product_type','price','factor_code','notes'].map(name=>[name,node()]));
  Object.assign(form.elements.price,{value:price,selectionStart:price.length,selectionEnd:price.length,selectionDirection:'none'});
  get('[data-draft-banner]').hidden=true;
  const document={body:{dataset:{teamUser:'7'}},documentElement:{classList:{add(){}}},activeElement:form.elements.price,
    querySelector:selector=>['[data-photo-dialog]','[data-profile-photo]','[data-profile-form]'].includes(selector)?null:get(selector),
    querySelectorAll:()=>[],addEventListener(){}};
  const indexedDB={open(){
    const request={result:{objectStoreNames:{contains:()=>true},transaction(){
      const transaction={objectStore:()=>({get:()=>({result:draft})})};
      queueMicrotask(()=>transaction.oncomplete?.());return transaction;
    }}};
    queueMicrotask(()=>request.onsuccess?.());return request;
  }};
  const window={indexedDB,FormData:function(){},XMLHttpRequest:function(){},
    URL:{createObjectURL:()=> 'blob:synthetic',revokeObjectURL(){}},addEventListener(){}};
  vm.runInNewContext(source,{document,window,indexedDB,URL:window.URL,
    setTimeout:()=>1,clearTimeout(){},queueMicrotask,DataTransfer:class{constructor(){this.items={add(){}};this.files=[];}}});
  for(let i=0;i<8;i++)await Promise.resolve();
  return {form,get,document,edit(value,start=value.length,end=start,direction='none'){
    Object.assign(form.elements.price,{value,selectionStart:start,selectionEnd:end,selectionDirection:direction});
    form.emit('input',{target:form.elements.price});return form.elements.price;
  }};
}

for(const value of ['۱۲٫۵','-۲۵۰۰۰۰','12.50','250e3','۳۰۰۰۰۰ تومان']){
  test('invalid price remains visible for validation rather than changing amount: '+value,async()=>{
    const f=await fixture();const input=f.edit(value);assert.equal(input.value,value);
    assert.equal(f.get('[data-price-readout]').textContent,'');
    assert.ok(input.validationMessage);
  });
}
test('valid Persian prices group without losing any digit or selection',async()=>{
  const f=await fixture();const input=f.edit('۱۲۳۴۵۶۷',2,5,'backward');
  assert.equal(input.value,'1,234,567');assert.equal(input.selectionStart,3);assert.equal(input.selectionEnd,7);assert.equal(input.selectionDirection,'backward');
});
test('restored nonempty private note is revealed for review before resubmission',async()=>{
  const f=await fixture({draft:{fields:{submission_key:'synthetic-key',notes:'private synthetic note',price:'250000'}}});
  f.get('[data-restore-draft]').emit('click');
  assert.equal(f.form.elements.notes.value,'private synthetic note');
  assert.equal(f.get('.optional-details').open,true);
  assert.equal(f.form.elements.submission_key.value,'synthetic-key');
});
test('restoring a draft without a note keeps the optional section collapsed',async()=>{
  const f=await fixture({draft:{fields:{submission_key:'synthetic-key',notes:''}}});
  f.get('[data-restore-draft]').emit('click');assert.equal(f.get('.optional-details').open,false);
});
