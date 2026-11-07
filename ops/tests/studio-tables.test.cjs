const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync('main/static/main/js/pages/studio.js','utf8');

function fixture({mobile=false,failed=false,aborted=false}={}){
  const handlers={};const focused=[],assigned=[],dispatched=[];let replaced=false,requested;
  const classes={add(){},remove(){},toggle(){}};
  const summary={focus:()=>focused.push('summary')};
  const header={dataset:{sortKey:'price'},closest:()=>null,focus:()=>focused.push('header')};
  const closedChoice={dataset:{sortKey:'price'},closest:s=>s==='.app-mobile-sort'?{}:null,focus(){}};
  const next={classList:classes,querySelector:s=>s==='.app-mobile-sort summary'?summary:null,
    querySelectorAll:s=>s==='[data-sort-link]'?[closedChoice,header]:[],setAttribute(){},focus(){},scrollIntoView(){}};
  const region={id:'products-table',classList:classes,setAttribute(){},removeAttribute(){},
    querySelector:()=>null,replaceWith:node=>{assert.equal(node,next);replaced=true;}};
  const location={href:'https://example.test/studio/products/?period=30&q=gift&page=3&issues_sort=date',assign:url=>assigned.push(String(url))};
  const link={href:'https://example.test/studio/products/?sort=price&dir=asc',dataset:{sortKey:'price'},
    closest:s=>s==='[data-sort-link],[data-page-link]'?link:s==='[data-table-region]'?region:s==='.app-mobile-sort'&&mobile?{}:null,
    hasAttribute:name=>name==='data-sort-link'};
  const document={body:{classList:classes},querySelector:()=>null,querySelectorAll:()=>[],
    addEventListener:(name,fn)=>(handlers[name]??=[]).push(fn),dispatchEvent:event=>dispatched.push(event.type)};
  const window={location,fetch:true,matchMedia:()=>({matches:false,addEventListener(){}}),addEventListener(){}};
  const fetch=async url=>{requested=String(url);if(aborted)throw Object.assign(Error('canceled'),{name:'AbortError'});if(failed)throw Error('network');return {ok:true,text:async()=>'<synthetic-table>'};};
  vm.runInNewContext(source,{window,document,URL,AbortController,fetch,
    Event:class{constructor(type){this.type=type;}},
    DOMParser:class{parseFromString(){return {getElementById:()=>next};}},
    history:{pushState:(state,title,url)=>{location.href=String(url);}},matchMedia:()=>({matches:true})});
  return {focused,assigned,dispatched,get replaced(){return replaced;},get requested(){return requested;},
    async click(options={}){
      const event={target:link,button:0,preventDefault(){this.defaultPrevented=true;},...options};
      await Promise.all((handlers.click||[]).map(fn=>fn(event)));return event;
    }};
}
test('mobile sort returns focus to the closed menu summary after replacing its DOM',async()=>{
  const f=fixture({mobile:true});await f.click();assert.equal(f.replaced,true);assert.deepEqual(f.focused,['summary']);
});
test('desktop sort returns focus to its header rather than an unfocusable mobile choice',async()=>{
  const f=fixture();await f.click();assert.deepEqual(f.focused,['header']);
});
test('sorting retains existing search, range and other-table sort while resetting page',async()=>{
  const f=fixture();await f.click();const url=new URL(f.requested);
  assert.equal(url.searchParams.get('q'),'gift');assert.equal(url.searchParams.get('period'),'30');
  assert.equal(url.searchParams.get('issues_sort'),'date');assert.equal(url.searchParams.get('sort'),'price');
  assert.equal(url.searchParams.get('dir'),'asc');assert.equal(url.searchParams.has('page'),false);
  assert.deepEqual(f.dispatched,['panel:save','panel:table-ready']);
});
test('network failure falls back to the complete server URL with the same filters',async()=>{
  const f=fixture({failed:true});await f.click();assert.equal(f.assigned.length,1);
  assert.equal(new URL(f.assigned[0]).searchParams.get('q'),'gift');assert.equal(f.replaced,false);
});
test('a superseded table request cannot navigate away from the newer interaction',async()=>{
  const f=fixture({aborted:true});await f.click();assert.deepEqual(f.assigned,[]);assert.equal(f.replaced,false);
});
test('modifier clicks retain normal browser new-tab behavior',async()=>{
  const f=fixture();const event=await f.click({ctrlKey:true});assert.equal(event.defaultPrevented,undefined);assert.equal(f.requested,undefined);
});
