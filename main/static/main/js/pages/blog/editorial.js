(function () {
  "use strict";
  var article = document.querySelector("[data-editorial-article]");
  if (!article) return;
  var preview = article.dataset.editorialPreview === "true";
  var toc = article.querySelector(".zad-article__toc");
  // Keep the first mobile screen focused on the article; native details works without JS.
  if (toc && window.matchMedia("(max-width: 700px)").matches) toc.open = false;
  if (toc && "IntersectionObserver" in window) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        toc.querySelectorAll("a").forEach(function (link) {
          if (link.hash === "#" + entry.target.id) link.setAttribute("aria-current", "location");
          else link.removeAttribute("aria-current");
        });
      });
    }, { rootMargin: "-15% 0px -60% 0px" });
    article.querySelectorAll(".zad-article__body h2[id]").forEach(function (heading) { observer.observe(heading); });
  }
  function track(name, destination) {
    if (!preview && window.zadAnalytics && typeof window.zadAnalytics.track === "function") {
      // Use a fixed destination category, never a URL that may contain a contact or query string.
      window.zadAnalytics.track(name, {
        article_id: article.dataset.editorialArticle,
        destination: destination
      });
    }
  }
  article.addEventListener("click", function (event) {
    var link = event.target.closest("a[data-editorial-link]");
    if (link && article.contains(link)) track("article_next_step", link.dataset.editorialLink);
  });
  var copy = article.querySelector("[data-editorial-copy]");
  if (copy && navigator.clipboard && window.isSecureContext && !preview) {
    copy.hidden = false;
    copy.addEventListener("click", function () {
      copy.disabled = true;
      var canonical = document.querySelector('link[rel="canonical"]');
      var address = canonical ? canonical.href : window.location.origin + window.location.pathname;
      navigator.clipboard.writeText(address).then(function () {
        article.querySelector("[data-copy-status]").textContent = "لینک مطلب کپی شد.";
        track("article_share", "copy_link");
      }).catch(function () {
        article.querySelector("[data-copy-status]").textContent = "کپی خودکار انجام نشد؛ می‌توانید آدرس صفحه را از مرورگر کپی کنید.";
      }).finally(function () {
        copy.disabled = false;
      });
    });
  }
})();
