# Responsive/UI replacement decision

**Code-level decision: PASS for replacement.**

The archive passes the available static/syntax/structure gates and the blocking issues found in the first responsive pass have been corrected.

## Pass gates
- CSS syntax: PASS
- JavaScript syntax: PASS
- Python syntax/compile: PASS
- Base viewport configuration: PASS
- 320px minimum layout contract: PASS by CSS contract
- Fluid container/gutter system: PASS
- Mobile form size/font contract: PASS
- Primary touch-target contract: PASS
- Carousel dot hit-area implementation: PASS (effective 44px target without changing visible dot size)
- Safe-area support: PASS
- Mobile dynamic viewport units: PASS
- Reduced-motion handling: PASS
- Keyboard focus visibility: PASS
- Navbar dropdown ARIA + Escape behavior: PASS
- Semantic main landmark structure: PASS
- Product responsive image `sizes`: PASS for the two-column mobile product grid
- Original media references preserved: PASS

## Not claimable from this media-stripped archive
- Pixel-perfect crop validation of real hero/product/gallery images.
- Runtime Django checks/tests because Django and the production dependencies are not available in this sandbox.
- Full browser visual regression across every page; the sandbox Chromium renderer stalls before reliable metric capture.

Those are runtime/visual validation items, not known code blockers in this archive.
