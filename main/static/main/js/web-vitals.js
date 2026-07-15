(function () {
  "use strict";

  if (!("PerformanceObserver" in window)) return;

  var lcpValue = null;
  var clsValue = 0;
  var clsSessionValue = 0;
  var clsSessionStart = 0;
  var clsLastEntryTime = 0;
  var interactions = new Map();
  var sent = false;

  function rating(name, value) {
    var thresholds = {
      LCP: [2500, 4000],
      INP: [200, 500],
      CLS: [0.1, 0.25],
    }[name];
    if (!thresholds) return "unknown";
    if (value <= thresholds[0]) return "good";
    if (value <= thresholds[1]) return "needs_improvement";
    return "poor";
  }

  function track(name, value) {
    if (value === null || typeof value === "undefined" || !isFinite(value)) return;
    var rounded = name === "CLS" ? Math.round(value * 1000) / 1000 : Math.round(value);
    var params = {
      metric_name: name,
      metric_value: rounded,
      metric_rating: rating(name, value),
      metric_source: "browser_rum",
      non_interaction: true,
    };
    if (window.zadAnalytics && typeof window.zadAnalytics.track === "function") {
      window.zadAnalytics.track("web_vital", params);
    }
  }

  function observe(type, callback, options) {
    try {
      var observer = new PerformanceObserver(function (list) {
        list.getEntries().forEach(callback);
      });
      observer.observe(Object.assign({ type: type, buffered: true }, options || {}));
      return observer;
    } catch (error) {
      return null;
    }
  }

  var lcpObserver = observe("largest-contentful-paint", function (entry) {
    lcpValue = entry.startTime;
  });

  observe("layout-shift", function (entry) {
    if (entry.hadRecentInput) return;

    var withinSession =
      clsSessionStart &&
      entry.startTime - clsLastEntryTime < 1000 &&
      entry.startTime - clsSessionStart < 5000;

    if (withinSession) {
      clsSessionValue += entry.value;
    } else {
      clsSessionValue = entry.value;
      clsSessionStart = entry.startTime;
    }
    clsLastEntryTime = entry.startTime;
    clsValue = Math.max(clsValue, clsSessionValue);
  });

  observe(
    "event",
    function (entry) {
      if (!entry.interactionId) return;
      var previous = interactions.get(entry.interactionId) || 0;
      interactions.set(entry.interactionId, Math.max(previous, entry.duration));
    },
    { durationThreshold: 40 }
  );

  function estimatedInp() {
    if (!interactions.size) return null;
    var values = Array.from(interactions.values()).sort(function (a, b) {
      return b - a;
    });
    var interactionCount =
      typeof performance.interactionCount === "number"
        ? performance.interactionCount
        : interactions.size;
    var percentileIndex = Math.min(Math.floor(interactionCount / 50), values.length - 1);
    return values[percentileIndex];
  }

  function stopLcpCollection() {
    if (lcpObserver) {
      try {
        lcpObserver.takeRecords().forEach(function (entry) {
          lcpValue = entry.startTime;
        });
        lcpObserver.disconnect();
      } catch (error) {
        // Ignore unsupported observer operations.
      }
    }
  }

  function flush() {
    if (sent) return;
    sent = true;
    stopLcpCollection();
    track("LCP", lcpValue);
    track("CLS", clsValue);
    track("INP", estimatedInp());
  }

  ["keydown", "click", "pointerdown"].forEach(function (eventName) {
    window.addEventListener(eventName, stopLcpCollection, { once: true, capture: true });
  });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flush();
  });
  window.addEventListener("pagehide", flush);
})();
