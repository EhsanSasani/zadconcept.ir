export function initFilterLinks() {
  document.addEventListener("click", function (event) {
    var link = event.target.closest("a[data-filter-target]");
    if (!link || event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    event.preventDefault();
    window.location.assign(link.dataset.filterTarget);
  });
}

initFilterLinks();
