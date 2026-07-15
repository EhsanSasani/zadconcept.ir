(function () {
  window.dataLayer = window.dataLayer || [];

  function pushEvent(eventName, params) {
    if (typeof window.gtag === "function") {
      var gtagParams = Object.assign({}, params || {});
      window.gtag("event", eventName, gtagParams);
      return;
    }

    var payload = Object.assign({ event: eventName }, params || {});
    window.dataLayer.push(payload);
  }

  function currentPageType() {
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

  function trafficSource() {
    var referrer = (document.referrer || "").toLowerCase();
    if (referrer.indexOf("chatgpt.com") !== -1 || referrer.indexOf("openai.com") !== -1) {
      return "chatgpt";
    }
    if (referrer.indexOf("perplexity.ai") !== -1) {
      return "perplexity";
    }
    if (referrer.indexOf("claude.ai") !== -1) {
      return "claude";
    }
    return null;
  }

  var initialPageParams = {
    page_type: currentPageType(),
    item_id: currentItemId(),
    traffic_source: trafficSource(),
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
