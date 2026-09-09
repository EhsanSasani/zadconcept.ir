const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../main/static/main/js/layout/overlays.js'), 'utf8');

function fixture() {
  const events = {};
  const viewportEvents = {};
  let document;
  function node(tag = 'DIV') {
    return {
      tagName: tag, children: [], parentElement: null, inert: false, hidden: false, isConnected: true,
      style: { overflow: '', overscrollBehavior: '', position: '', top: '', left: '', right: '', width: '', scrollBehavior: '',
        setProperty(key, value) { this[key] = value; }, removeProperty(key) { delete this[key]; } },
      append(child) { child.parentElement = this; this.children.push(child); return child; },
      contains(child) { return child === this || this.children.some((item) => item.contains(child)); },
      closest() { for (let item = this; item; item = item.parentElement) if (item.inert || item.hidden) return item; return null; },
      querySelectorAll() { return this.children.filter((item) => item.tagName === 'BUTTON'); },
      hasAttribute() { return false; }, getClientRects() { return [{}]; },
      focus() { document.activeElement = this; },
    };
  }
  document = { documentElement: node('HTML'), body: node('BODY'), addEventListener(name, callback) { events[name] = callback; } };
  const window = { scrollX: 0, scrollY: 740, innerHeight: 800,
    visualViewport: { height: 720, offsetTop: 0, addEventListener(name, cb) { viewportEvents[name] = cb; } },
    getComputedStyle() { return { visibility: 'visible' }; }, matchMedia() { return { matches: false }; },
    addEventListener() {}, scrollTo(x, y) { this.lastScroll = [x, y]; },
  };
  const page = document.body.append(node('MAIN'));
  const opener = page.append(node('BUTTON'));
  const menu = document.body.append(node());
  const first = menu.append(node('BUTTON'));
  const last = menu.append(node('BUTTON'));
  const viewer = document.body.append(node());
  const viewerClose = viewer.append(node('BUTTON'));
  const protectedNode = document.body.append(node()); protectedNode.inert = true;
  document.activeElement = opener;
  vm.runInNewContext(source, { document, window });
  return { api: window.ZadOverlays, document, window, page, opener, menu, first, last, viewer, viewerClose, protectedNode, events, viewportEvents };
}

test('closing nested image viewer keeps page locked and restores parent focus', () => {
  const f = fixture();
  f.api.open(f.menu, { focus: f.first });
  assert.equal(f.page.inert, true);
  assert.equal(f.document.body.style.top, '-740px');
  f.api.open(f.viewer, { focus: f.viewerClose });
  assert.equal(f.menu.inert, true);
  f.api.close(f.viewer);
  assert.equal(f.page.inert, true);
  assert.equal(f.menu.inert, false);
  assert.equal(f.document.activeElement, f.first);
  assert.equal(f.document.body.style.position, 'fixed');
  f.api.close(f.menu);
  assert.equal(f.page.inert, false);
  assert.equal(f.protectedNode.inert, true);
  assert.equal(f.document.activeElement, f.opener);
  assert.equal(f.document.body.style.position, '');
  assert.deepEqual(f.window.lastScroll, [0, 740]);
});

test('duplicate open and close do not lose original scroll state', () => {
  const f = fixture();
  f.document.body.style.overflow = 'clip';
  f.api.open(f.menu); f.api.open(f.menu);
  f.api.close(f.menu); f.api.close(f.menu);
  assert.equal(f.document.body.style.overflow, 'clip');
  assert.equal(f.page.inert, false);
  assert.deepEqual(f.window.lastScroll, [0, 740]);
});

test('Tab wraps focus and Escape closes only top overlay', () => {
  const f = fixture(); let menuCloses = 0; let viewerCloses = 0;
  f.api.open(f.menu, { focus: f.first, onClose: () => menuCloses++ });
  f.last.focus(); let prevented = false;
  f.events.keydown({ key: 'Tab', shiftKey: false, preventDefault() { prevented = true; } });
  assert.equal(prevented, true); assert.equal(f.document.activeElement, f.first);
  f.api.open(f.viewer, { focus: f.viewerClose, onClose: () => viewerCloses++ });
  f.events.keydown({ key: 'Escape', preventDefault() {}, stopImmediatePropagation() {} });
  assert.equal(menuCloses, 0); assert.equal(viewerCloses, 1);
});

test('mobile keyboard changes bounds and final close clears viewport variables', () => {
  const f = fixture(); f.api.open(f.menu);
  f.window.visualViewport.height = 340; f.window.visualViewport.offsetTop = 25;
  f.viewportEvents.resize();
  assert.equal(f.document.documentElement.style['--zad-overlay-height'], '340px');
  assert.equal(f.document.documentElement.style['--zad-overlay-top'], '25px');
  f.api.close(f.menu);
  assert.equal(f.document.documentElement.style['--zad-overlay-height'], undefined);
});
