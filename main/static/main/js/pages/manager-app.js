(() => {
  'use strict';
  // Derive card labels from the same table headings; keep one set of forms/IDs.
  function enhanceTables(root = document) {
    root.querySelectorAll('.studio-table').forEach(table => {
      const heads = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
      if (!heads.length) return;
      table.classList.add('app-responsive-table');
      table.querySelectorAll('tbody tr').forEach(row => {
        [...row.children].forEach((cell, i) => {
          if (!cell.hasAttribute('colspan')) cell.dataset.label = heads[i] || '';
        });
      });
    });
  }
  enhanceTables();
  const main = document.getElementById('studio-main');
  if (main) new MutationObserver(changes => {
    for (const change of changes) for (const node of change.addedNodes) {
      if (node.nodeType === Node.ELEMENT_NODE) enhanceTables(node);
    }
  }).observe(main, {childList:true, subtree:true});
  // Internal return preserves the visitor's actual filters and report period.
  document.querySelectorAll('[data-app-back]').forEach(link => {
    link.addEventListener('click', event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      try {
        const previous = new URL(document.referrer);
        if (previous.origin === location.origin && previous.pathname.startsWith('/studio/') && history.length > 1) {
          event.preventDefault(); history.back();
        }
      } catch { /* Direct entry uses the real fallback URL. */ }
    });
  });
  // On invalid forms, reveal the section and focus its first error.
  const invalid = document.querySelector('.has-error input, .has-error select, .has-error textarea');
  if (invalid) {
    for (let parent = invalid.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
    invalid.focus();
  }
  document.querySelectorAll('form[data-confirm-account]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirmAccount)) event.preventDefault();
    });
  });
})();
(() => {
  const plot=document.querySelector('[data-metric-plot]');
  const source=document.getElementById('app-metric-data');
  if(!plot || !source) return;
  let rows;try{rows=JSON.parse(source.textContent);}catch{return;}
  if(!rows.length)return;
  const ns='http://www.w3.org/2000/svg';
  const make=(tag,attrs,text)=>{const el=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,String(v));if(text!==undefined)el.textContent=text;return el;};
  const w=Math.max(320,rows.length*30+40),h=220,baseline=175,top=24;
  const max=Math.max(1,...rows.map(r=>Number(r.value)||0));
  const svg=make('svg',{viewBox:`0 0 ${w} ${h}`,width:w,height:h,role:'img','aria-label':'نمودار روزانه؛ مقادیر دقیق در جدول زیر نمودار'});
  for(let i=0;i<=3;i++)svg.append(make('line',{x1:20,x2:w-20,y1:top+(baseline-top)*i/3,y2:top+(baseline-top)*i/3,class:'plot-grid'}));
  const step=(w-40)/rows.length;
  const dates=new Intl.DateTimeFormat('fa-IR',{month:'2-digit',day:'2-digit',timeZone:'Asia/Tehran'});
  rows.forEach((r,i)=>{
    const value=Number(r.value)||0,bh=value/max*(baseline-top),x=20+i*step;
    const bar=make('rect',{x:x+step*.18,y:baseline-bh,width:step*.64,height:bh,rx:3,class:'plot-bar'});
    const date=dates.format(new Date(r.day+'T12:00:00Z'));
    bar.append(make('title',{},`${date}: ${value.toLocaleString('fa-IR')}`));svg.append(bar);
    if(rows.length<=8)svg.append(make('text',{x:x+step/2,y:Math.max(16,baseline-bh-8),'text-anchor':'middle'},value.toLocaleString('fa-IR')));
    if(i%Math.max(1,Math.ceil(rows.length/14))===0)svg.append(make('text',{x:x+step/2,y:205,'text-anchor':'middle'},date));
  });
  plot.append(svg);
})();
