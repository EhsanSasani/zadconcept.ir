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
  const money=plot.dataset.money==='true';
  const compact=rows.length<=7;
  plot.classList.toggle('app-metric-plot-fit',compact);
  let lastWidth=0;
  function render(){
  const availableWidth=plot.clientWidth;
  if(!availableWidth || availableWidth===lastWidth)return;
  lastWidth=availableWidth;
  const left=compact?36:58,right=8,h=240,baseline=190,top=38;
  const w=compact?availableWidth:Math.max(320,availableWidth,rows.length*(money?64:42)+left+right);
  const peak=Math.max(1,...rows.map(r=>Number(r.value)||0));
  const tick=Math.max(1,Math.ceil(peak/3)),max=tick*3;
  const format=value=>value>=1000000?`${(value/1000000).toLocaleString('fa-IR',{maximumFractionDigits:1})} م`:value>=1000?`${(value/1000).toLocaleString('fa-IR',{maximumFractionDigits:1})} ه`:value.toLocaleString('fa-IR');
  const svg=make('svg',{viewBox:`0 0 ${w} ${h}`,width:w,height:h,role:'img','aria-label':'نمودار روزانه؛ مقادیر دقیق در جدول زیر نمودار'});
  for(let i=0;i<=3;i++){
    const y=top+(baseline-top)*i/3;
    svg.append(make('line',{x1:left,x2:w-right,y1:y,y2:y,class:'plot-grid'}));
    svg.append(make('text',{x:left-10,y:y+4,'text-anchor':'end',class:'plot-axis'},format(max-i*tick)));
  }
  const step=(w-left-right)/rows.length;
  const dates=new Intl.DateTimeFormat('fa-IR',{month:'2-digit',day:'2-digit',timeZone:'Asia/Tehran'});
  rows.forEach((r,i)=>{
    const value=Number(r.value)||0,bh=value/max*(baseline-top),x=left+i*step;
    const barWidth=Math.min(40,step*.56);
    const bar=make('rect',{x:x+(step-barWidth)/2,y:baseline-bh,width:barWidth,height:bh,rx:6,class:'plot-bar'});
    const date=dates.format(new Date(r.day+'T12:00:00Z'));
    bar.append(make('title',{},`${date}: ${value.toLocaleString('fa-IR')}`));svg.append(bar);
    svg.append(make('text',{x:x+step/2,y:Math.max(20,baseline-bh-10),'text-anchor':'middle',class:'plot-value'},format(value)));
    svg.append(make('text',{x:x+step/2,y:219,'text-anchor':'middle',class:'plot-date'},date));
  });
  plot.replaceChildren(svg);
  }
  render();
  new ResizeObserver(render).observe(plot);
})();
