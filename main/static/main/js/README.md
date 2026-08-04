# JavaScript architecture

The site uses browser-native ES modules. There is no production bundler and no
runtime framework dependency.

## Boundaries

- `site.js`: global entry point; starts navigation and hero behavior.
- `core/`: DOM-independent or broadly reusable behavior such as motion policy,
  swipe recognition, and carousel state.
- `components/`: one reusable UI component per module.
- `pages/`: behavior that belongs to a single page/domain.
- `analytics.js` and `web-vitals.js`: intentionally isolated classic scripts
  because they expose/consume `window.zadAnalytics`.

## Rules

1. HTML must remain usable without JavaScript. Enhancements attach to `data-*`
   hooks; CSS class names are not JavaScript APIs.
2. Do not clone interactive DOM to simulate infinite rails.
3. Do not convert vertical wheel input into horizontal scrolling.
4. Any animation or smooth scroll must honor `prefers-reduced-motion`.
5. Timed rotation must pause for focus, hover, hidden documents, and reduced
   motion. It must use the shared carousel/motion utilities.
6. Page code may import `core/` and `components/`; shared modules must not import
   page modules.
7. Run `npm run lint:js` and `npm run test:js` before committing behavior.
