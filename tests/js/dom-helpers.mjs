import { JSDOM } from "jsdom";

export function installDom(markup, { reducedMotion = true } = {}) {
  const dom = new JSDOM(markup, {
    pretendToBeVisual: true,
    url: "https://www.zadconcept.ir/",
  });

  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    disconnect() {}
  };
  window.matchMedia = () => ({
    matches: reducedMotion,
    addEventListener() {},
    removeEventListener() {},
  });
  window.requestAnimationFrame = (callback) => callback();

  return () => {
    dom.window.close();
    delete globalThis.ResizeObserver;
    delete globalThis.document;
    delete globalThis.window;
  };
}
