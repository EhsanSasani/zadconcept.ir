(function () {
  const filterRoot = document.querySelector("[data-catalog-filter]");
  const grid = document.querySelector("[data-catalog-grid]");
  const loader = document.querySelector("[data-catalog-loader]");
  const status = document.querySelector("[data-catalog-loader-status]");
  const loadMoreButton = document.querySelector("[data-catalog-load-more]");
  const scrollbarThumb = document.querySelector(".flowers-filter-scrollbar span");

  if (!filterRoot || !grid || !loader) return;

  let loading = false;
  let hasNext = loader.dataset.hasNext === "true";
  let nextPage = Number(loader.dataset.nextPage || "0");
  let currentCategory = loader.dataset.category || "";
  let controller = null;
  let requestSequence = 0;

  function setStatus(text) {
    if (status) status.textContent = text || "";
  }

  function syncLoadMoreButton(errorMode) {
    if (!loadMoreButton) return;

    loadMoreButton.hidden = !errorMode && !hasNext;
    loadMoreButton.textContent = errorMode ? "تلاش دوباره" : "نمایش محصولات بیشتر";
  }

  function updateFilterScrollbar() {
    if (!scrollbarThumb) return;

    const maxScroll = filterRoot.scrollWidth - filterRoot.clientWidth;
    if (maxScroll <= 0) {
      scrollbarThumb.parentElement.style.display = "none";
      return;
    }

    scrollbarThumb.parentElement.style.display = "block";
    const trackWidth = scrollbarThumb.parentElement.clientWidth;
    const maxThumbMove = trackWidth - 16;
    const progress = Math.min(1, Math.max(0, Math.abs(filterRoot.scrollLeft) / maxScroll));
    scrollbarThumb.style.transform = `translateX(${progress * maxThumbMove}px)`;
  }

  function buildUrl(page, category) {
    const url = new URL(loader.dataset.loadUrl, window.location.origin);
    url.searchParams.set("partial", "products");
    url.searchParams.set("page", String(page));

    if (category) url.searchParams.set("category", category);
    return url;
  }

  function resetPagination(data) {
    hasNext = Boolean(data.has_next);
    nextPage = Number(data.next_page || "0");
    loader.dataset.hasNext = hasNext ? "true" : "false";
    loader.dataset.nextPage = nextPage ? String(nextPage) : "";
    setStatus("");
    syncLoadMoreButton(false);
  }

  function maybeLoadNextPage() {
    if (!hasNext || !nextPage || loading) return;

    const rect = loader.getBoundingClientRect();
    if (rect.top <= window.innerHeight + 420 && rect.bottom >= -420) {
      loadPage(nextPage, currentCategory, "append");
    }
  }

  async function loadPage(page, category, mode) {
    const replacing = mode === "replace";
    if (loading && !replacing) return false;

    if (controller) controller.abort();
    controller = new AbortController();
    const requestId = ++requestSequence;

    loading = true;
    loader.classList.add("is-loading");
    setStatus("در حال بارگذاری محصولات...");
    syncLoadMoreButton(false);

    try {
      const response = await fetch(buildUrl(page, category), {
        headers: {"X-Requested-With": "XMLHttpRequest"},
        signal: controller.signal,
      });

      if (!response.ok) throw new Error("Catalog request failed");
      const data = await response.json();

      if (requestId !== requestSequence) return false;

      if (replacing) {
        grid.innerHTML = data.html;
      } else {
        grid.insertAdjacentHTML("beforeend", data.html);
      }

      resetPagination(data);
      window.requestAnimationFrame(maybeLoadNextPage);
      return true;
    } catch (error) {
      if (error.name !== "AbortError" && requestId === requestSequence) {
        setStatus("بارگذاری انجام نشد.");
        syncLoadMoreButton(true);
      }
      return false;
    } finally {
      if (requestId === requestSequence) {
        loading = false;
        loader.classList.remove("is-loading");
      }
    }
  }

  function scrollToGridStart() {
    const gridTop = grid.getBoundingClientRect().top + window.pageYOffset - 110;
    window.scrollTo({top: gridTop, behavior: "smooth"});
  }

  filterRoot.addEventListener("click", async function (event) {
    const link = event.target.closest("[data-filter]");
    if (!link) return;

    event.preventDefault();
    const filter = link.dataset.filter || "all";
    const category = filter === "all" ? "" : filter;
    const success = await loadPage(1, category, "replace");
    if (!success) return;

    filterRoot.querySelectorAll("[data-filter]").forEach((item) => {
      item.classList.toggle("is-active", item === link);
    });

    currentCategory = category;
    loader.dataset.category = category;
    const targetUrl = category
      ? `${loader.dataset.loadUrl}?category=${encodeURIComponent(category)}`
      : loader.dataset.loadUrl;
    window.history.pushState({category}, "", targetUrl);
    scrollToGridStart();
  });

  filterRoot.addEventListener("wheel", function (event) {
    if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
    filterRoot.scrollLeft += event.deltaY;
    event.preventDefault();
  }, {passive: false});

  filterRoot.addEventListener("scroll", updateFilterScrollbar, {passive: true});
  window.addEventListener("resize", updateFilterScrollbar);
  window.addEventListener("popstate", function () {
    window.location.reload();
  });

  if (loadMoreButton) {
    loadMoreButton.addEventListener("click", function () {
      if (nextPage) loadPage(nextPage, currentCategory, "append");
    });
  }

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) maybeLoadNextPage();
    }, {rootMargin: "420px 0px"});
    observer.observe(loader);
  }

  updateFilterScrollbar();
  syncLoadMoreButton(false);
})();
