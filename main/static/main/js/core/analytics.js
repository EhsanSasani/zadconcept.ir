(function () {
  window.dataLayer = window.dataLayer || [];

  function pushEvent(eventName, params) {
    var eventParams = Object.assign({
      traffic_source: aiTrafficSource,
      ai_source: aiTrafficSource,
    }, params || {});
    if (typeof window.gtag === "function") {
      var gtagParams = Object.assign({}, eventParams);
      window.gtag("event", eventName, gtagParams);
      return;
    }

    var payload = Object.assign({ event: eventName }, eventParams);
    window.dataLayer.push(payload);
  }

  function currentPageType() {
    if (document.body && document.body.classList.contains("page-same-day")) {
      return "same_day";
    }
    return document.body && document.body.dataset.pageType ? document.body.dataset.pageType : "home";
  }

  function currentItemId() {
    return document.body && document.body.dataset.itemId ? document.body.dataset.itemId : null;
  }

  function ctaPosition(node) {
    return (node && node.dataset && node.dataset.ctaPosition) || "inline";
  }

  window.zadAnalytics = window.zadAnalytics || {};
  window.zadAnalytics.track = pushEvent;

  var aiSourceDomains = {
    "chatgpt.com": "chatgpt", "openai.com": "chatgpt",
    "perplexity.ai": "perplexity", "claude.ai": "claude",
    "gemini.google.com": "gemini", "copilot.microsoft.com": "copilot",
    "copilot.com": "copilot",
  };
  var aiStorageKey = "zad_ai_source_v1";
  var aiAttributionWindow = 30 * 60 * 1000;

  function sourceForHost(host) {
    return Object.keys(aiSourceDomains).reduce(function (found, domain) {
      return found || (host === domain || host.endsWith("." + domain) ? aiSourceDomains[domain] : null);
    }, null);
  }

  function forgetAiSource() {
    try { window.sessionStorage.removeItem(aiStorageKey); } catch (error) { /* Storage can be blocked. */ }
  }

  function rememberAiSource(source) {
    try {
      // Store only an allowlisted label and time, never a URL, prompt or identifier.
      window.sessionStorage.setItem(aiStorageKey, JSON.stringify({ source: source, at: Date.now() }));
    } catch (error) { /* Analytics must not interfere with browsing. */ }
    return source;
  }

  function trafficSource() {
    var currentUrl;
    var referrer;
    try { currentUrl = new URL(window.location.href); } catch (error) { return null; }
    var campaign = currentUrl.searchParams.get("utm_source");
    if (campaign) {
      var normalized = campaign.trim().toLowerCase();
      var campaignSource = sourceForHost(normalized) || (
        ["chatgpt", "perplexity", "claude", "gemini", "copilot"].indexOf(normalized) !== -1 ? normalized : null
      );
      if (campaignSource) { return rememberAiSource(campaignSource); }
      forgetAiSource();
      return null;
    }
    try { referrer = document.referrer ? new URL(document.referrer) : null; } catch (error) { referrer = null; }
    var source = referrer && /^https?:$/.test(referrer.protocol) ? sourceForHost(referrer.hostname) : null;
    if (source) { return rememberAiSource(source); }
    if (referrer && referrer.origin !== currentUrl.origin) {
      forgetAiSource();
      return null;
    }
    try {
      var saved = JSON.parse(window.sessionStorage.getItem(aiStorageKey) || "null");
      if (saved && Object.values(aiSourceDomains).indexOf(saved.source) !== -1 &&
          typeof saved.at === "number" && saved.at <= Date.now() && Date.now() - saved.at < aiAttributionWindow) {
        return saved.source;
      }
    } catch (error) { /* Missing or malformed session data is not a page error. */ }
    forgetAiSource();
    return null;
  }

  var aiTrafficSource = trafficSource();

  var initialPageParams = {
    page_type: currentPageType(),
    item_id: currentItemId(),
    traffic_source: aiTrafficSource,
  };
  pushEvent("zad_page_view", initialPageParams);

  if (currentItemId()) {
    pushEvent("view_item", {
      item_id: currentItemId(),
      item_name: document.body.dataset.itemName || null,
      item_category: document.body.dataset.itemCategory || null,
    });
  }

  if (document.querySelector("[data-lead-success]")) {
    pushEvent("generate_lead", {
      page_type: currentPageType(),
      item_id: currentItemId(),
    });
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest("a[href]");
    if (!link) {
      return;
    }

    var href = link.getAttribute("href") || "";
    var params = {
      page_type: currentPageType(),
      item_id: currentItemId(),
      cta_position: ctaPosition(link),
    };

    var productCard = link.closest("[data-catalog-card]") || link.closest("[data-zad-modal-card]");
    if (productCard) {
      pushEvent("select_item", {
        item_id: productCard.dataset.productCode || null,
        item_name: productCard.dataset.productName || productCard.dataset.productCode || null,
        item_category: productCard.dataset.productType || null,
        page_type: currentPageType(),
      });
    }

    if (href.indexOf("tel:") === 0) {
      pushEvent("click_to_call", params);
      return;
    }

    if (href.indexOf("t.me") !== -1 || href.indexOf("telegram") !== -1) {
      pushEvent("click_telegram", params);
      return;
    }

    if (href.indexOf("ble.ir") !== -1) {
      pushEvent("click_bale", params);
    }
  });

  document.addEventListener("submit", function (event) {
    var form = event.target.closest("form[data-track-lead-form]");
    if (!form) {
      return;
    }

    var leadField = form.querySelector('[name="lead_type"]');
    var leadType = leadField && leadField.value ? leadField.value : form.dataset.defaultLeadType || null;

    pushEvent("lead_form_submit", {
      page_type: currentPageType(),
      item_id: currentItemId(),
      cta_position: form.dataset.ctaPosition || "inline",
      lead_type: leadType,
    });
  });

  function toggleOptionalFields(form) {
    var leadType = form.querySelector('[name="lead_type"]');
    var deliveryWindow = form.querySelector('[name="delivery_window"]');
    var eventRow = form.querySelector(".event-only");
    var dateRow = form.querySelector(".date-only");

    if (!leadType || !deliveryWindow) {
      return;
    }

    function refresh() {
      if (eventRow) {
        eventRow.style.display = leadType.value === "event" ? "grid" : "none";
      }
      if (dateRow) {
        dateRow.style.display = deliveryWindow.value === "pick_date" ? "grid" : "none";
      }
    }

    leadType.addEventListener("change", refresh);
    deliveryWindow.addEventListener("change", refresh);
    refresh();
  }

  document.querySelectorAll("form[data-track-lead-form]").forEach(toggleOptionalFields);
})();
