const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync('main/static/main/js/components/panel-navigation.js','utf8');
const KEY='zad-panel-navigation:v1';
function fixture({url='/sales/?q=gift&page=2',user='42',storage=new Map(),type='navigate',blocked=false,referrer='',forms=[]}={}){
  const location=new URL(url,'https://example.test');const docs={},windows={};
  const back={href:'/sales/'};
  const table={scrollLeft:-70};const detail={id:'report-details',tagName:'DETAILS',open:false};
  const group={selected:'all',querySelector(selector){
    if(selector==='[aria-pressed="true"]')return {dataset:{productionFilter:this.selected}};
    const match=selector.match(/data-production-filter="(.*?)"/);if(!match)return null;
    return {getAttribute:()=>String(this.selected===match[1]),click:()=>{this.selected=match[1];}};
  }};
  const document={createElement:()=>({}),body:{dataset:{panelUser:user}},referrer,
    querySelectorAll(selector){
      if(selector==='form[data-panel-return]')return forms;
      if(selector==='[data-quick-filter]')return [group];
      if(selector==='details[id][open]')return detail.open?[detail]:[];
      if(selector==='.table-scroll')return [table];
      if(selector.includes('[data-app-back]'))return [back];return [];
    },getElementById:id=>id===detail.id?detail:null,
    addEventListener:(name,fn)=>(docs[name]??=[]).push(fn)};
  const window={scrollX:0,scrollY:0,scrollTo:({left,top})=>{window.scrollX=left;window.scrollY=top;},
    addEventListener:(name,fn)=>(windows[name]??=[]).push(fn)};
  const sessionStorage={getItem:k=>{if(blocked)throw Error('blocked');return storage.get(k)||null;},
    setItem:(k,v)=>{if(blocked)throw Error('blocked');storage.set(k,v);},removeItem:k=>{if(blocked)throw Error('blocked');storage.delete(k);}};
  vm.runInNewContext(source,{document,window,location,sessionStorage,URL,Date,
    performance:{getEntriesByType:()=>[{type}]},requestAnimationFrame:fn=>fn()});
  const emit=(events,name,event={})=>{for(const fn of events[name]||[])fn(event);};
  function click(href,{isBack=false,isDrilldown=false,main=true,...options}={}){
    const link={href:new URL(href,location.href).href,target:'',hasAttribute:()=>false,
      matches:selector=>selector==='[data-panel-drilldown]'?isDrilldown:isBack,
      closest:selector=>selector==='a[href]'?link:selector==='main'&&main?{}:null};
    emit(docs,'click',{target:link,button:0,...options});
  }
  return {storage,back,window,table,detail,group,location,click,
    doc:(name,event)=>emit(docs,name,event),win:(name,event)=>emit(windows,name,event),
    state:()=>JSON.parse(storage.get(KEY)||'null')};
}
test('back control preserves the exact parent query and restores its scroll',()=>{
  const list=fixture();list.window.scrollY=1250;list.table.scrollLeft=-140;
  list.click('/sales/products/8/');list.win('pagehide');
  const detail=fixture({url:'/sales/products/8/',storage:list.storage});
  assert.equal(detail.back.href,'/sales/?q=gift&page=2');
  detail.click(detail.back.href,{isBack:true});detail.win('pagehide');
  const returned=fixture({storage:list.storage});returned.win('pageshow',{});
  assert.equal(returned.window.scrollY,1250);assert.equal(returned.table.scrollLeft,-140);
});
test('a direct entry keeps its real server fallback instead of inventing an undefined URL',()=>{
  assert.equal(fixture({url:'/sales/products/8/'}).back.href,'/sales/');
});
test('same-page sorting and tabs preserve the logical parent instead of making a back loop',()=>{
  const dashboard=fixture({url:'/studio/?period=30'});dashboard.click('/studio/metrics/sold/?period=30');
  const report=fixture({url:'/studio/metrics/sold/?period=30',storage:dashboard.storage});
  report.click('/studio/metrics/sold/?period=30&sort=price');
  const sorted=fixture({url:'/studio/metrics/sold/?period=30&sort=price',storage:dashboard.storage});
  assert.equal(sorted.back.href,'/studio/?period=30');
});
test('an explicit same-route supplier drilldown can still return to its supplier list',()=>{
  const list=fixture({url:'/studio/procurement/purchases/?period=30'});
  list.click('/studio/procurement/purchases/?period=30&supplier=synthetic',{isDrilldown:true});
  const supplier=fixture({url:'/studio/procurement/purchases/?period=30&supplier=synthetic',storage:list.storage});
  assert.equal(supplier.back.href,'/studio/procurement/purchases/?period=30');
});
test('native history restores quick filters and explicitly open report sections',()=>{
  const list=fixture();list.group.selected='CUSTOM';list.detail.open=true;list.window.scrollY=600;
  list.win('pagehide');const returned=fixture({storage:list.storage,type:'back_forward'});
  returned.win('pageshow',{});assert.equal(returned.group.selected,'CUSTOM');
  assert.equal(returned.detail.open,true);assert.equal(returned.window.scrollY,600);
});
test('expired private state is discarded',()=>{
  const storage=new Map([[KEY,JSON.stringify({user:'42',pages:[{url:'/sales/?q=gift&page=2',at:Date.now()-1800001,y:900}]})]]);
  const page=fixture({storage,type:'back_forward'});page.win('pageshow',{});
  assert.equal(page.window.scrollY,0);assert.equal(page.state().pages.length,0);
});
test('changing staff accounts cannot reuse another users navigation state',()=>{
  const page=fixture();page.window.scrollY=900;page.win('pagehide');
  const next=fixture({storage:page.storage,user:'43',type:'back_forward'});next.win('pageshow',{});
  assert.equal(next.window.scrollY,0);assert.equal(next.state().user,'43');assert.equal(next.state().pages.length,0);
});
test('anonymous login clears stored private navigation',()=>{
  const page=fixture();page.win('pagehide');fixture({storage:page.storage,user:''});assert.equal(page.storage.has(KEY),false);
});
for(const options of [{ctrlKey:true},{metaKey:true},{shiftKey:true},{altKey:true},{button:1},{defaultPrevented:true}]){
  test('modified or canceled link is left to the browser '+JSON.stringify(options),()=>{
    const page=fixture();page.click('/sales/products/8/',options);assert.equal(page.state().pending,undefined);
  });
}
for(const href of ['https://evil.test/studio/','//evil.test/studio/','/studio/logout/','/studio/products/8/delete/','/procurement/purchases/1/void/']){
  test('unsupported or unsafe target never becomes a return destination '+href,()=>{
    const page=fixture();page.click(href);assert.equal(page.state().pending,undefined);
  });
}
test('blocked session storage leaves ordinary navigation usable',()=>{
  const page=fixture({blocked:true});page.click('/sales/products/8/');page.win('pagehide');assert.equal(page.back.href,'/sales/');
});
test('POST redirect retains the list parent without reading form field values',()=>{
  const list=fixture();list.click('/sales/products/8/');
  const detail=fixture({url:'/sales/products/8/',storage:list.storage});
  const form={method:'post',action:{name:'action',value:'sell'},getAttribute:()=>'',elements:{secret:'PRIVATE-FORM-VALUE'}};
  detail.doc('submit',{target:form});
  assert.equal(JSON.stringify(detail.state()).includes('PRIVATE-FORM-VALUE'),false);
  const returned=fixture({url:'/sales/products/8/',referrer:'https://example.test/sales/products/8/',storage:detail.storage});
  assert.equal(returned.back.href,'/sales/?q=gift&page=2');
});
test('a canceled confirmation does not create submission navigation',()=>{
  const page=fixture();page.doc('submit',{defaultPrevented:true,target:{}});assert.equal(page.state().pending,undefined);
});
test('logout clears state without intercepting or replaying the POST',()=>{
  const page=fixture();page.win('pagehide');
  page.doc('submit',{target:{method:'post',getAttribute:()=>'/studio/logout/'}});
  page.win('pagehide');page.win('pageshow',{persisted:true});
  assert.equal(page.storage.has(KEY),false);
});
test('AJAX history saves the old URL before replacing a table',()=>{
  const page=fixture({url:'/studio/products/?page=1'});page.window.scrollY=700;page.group.selected='DAILY';
  page.doc('panel:save');page.location.search='?page=2';page.doc('panel:table-ready');
  page.window.scrollY=300;page.location.search='?page=1';page.win('popstate');page.win('pagehide');
  const returned=fixture({url:'/studio/products/?page=1',storage:page.storage,type:'reload'});returned.win('pageshow',{});
  assert.equal(returned.window.scrollY,700);assert.equal(returned.group.selected,'DAILY');
});
test('restoration never overrides a deliberate user scroll or key interaction',()=>{
  const page=fixture();page.window.scrollY=900;page.win('pagehide');
  const returned=fixture({storage:page.storage,type:'back_forward'});returned.win('wheel');returned.win('pageshow',{});
  assert.equal(returned.window.scrollY,0);
});
test('BFCache refresh marks restoration before existing workspace freshness reload',()=>{
  const page=fixture();page.window.scrollY=800;page.win('pagehide');page.win('pageshow',{persisted:true});
  assert.equal(page.state().pending.kind,'return');
  const fresh=fixture({storage:page.storage,type:'reload'});fresh.win('pageshow',{});assert.equal(fresh.window.scrollY,800);
});

function returnForm(mode) {
  let input;
  return {method:'post', dataset:{panelReturn:mode}, getAttribute:()=>'',
    querySelector:()=>input, appendChild:node=>{input=node;}, get input(){return input;}};
}
test('confirmed row POST preserves exact list return metadata and restores scroll',()=>{
  const form=returnForm('self');
  const page=fixture({forms:[form]});page.window.scrollY=980;
  assert.equal(form.input.name,'return_to');assert.equal(form.input.type,'hidden');
  assert.equal(form.input.value,'/sales/?q=gift&page=2');
  page.doc('panel:submit',{detail:form});
  assert.equal(page.state().pending.returnTarget,'/sales/?q=gift&page=2');
  const returned=fixture({storage:page.storage,referrer:'https://example.test/sales/?q=gift&page=2'});
  returned.win('pageshow',{});assert.equal(returned.window.scrollY,980);
});
test('edit form returns to its exact parent and dynamically replaced forms are decorated',()=>{
  const list=fixture();list.click('/sales/products/8/');
  const form=returnForm('parent');
  const edit=fixture({url:'/sales/products/8/',storage:list.storage,forms:[form]});
  assert.equal(form.input.value,'/sales/?q=gift&page=2');
  const row=returnForm('self');
  const table=fixture({url:'/studio/products/?page=1',forms:[row]});
  table.location.search='?page=3';table.doc('panel:table-ready');
  assert.equal(row.input.value,'/studio/products/?page=3');
});
test('direct editor entry leaves the return destination empty for the server fallback',()=>{
  const form=returnForm('parent');fixture({forms:[form]});assert.equal(form.input.value,'');
});
