(() => {
  "use strict";
  const $ = (selector, root = document) => root.querySelector(selector);
  const announce = (message) => {
    const node = $("[data-announcer]");
    if (node) node.textContent = message;
  };
  const menu = $("[data-menu]"),
    sidebar = $(".studio-sidebar"),
    backdrop = $("[data-backdrop]");
  const smallScreen = window.matchMedia("(max-width: 900px)");
  let menuOpen = false;
  function toggleMenu(open, restore = true) {
    menuOpen = open;
    sidebar?.classList.toggle("open", open);
    if (sidebar) sidebar.inert = smallScreen.matches && !open;
    if (backdrop) backdrop.hidden = !open;
    menu?.setAttribute("aria-expanded", String(open));
    document.body.classList.toggle("scroll-locked", open);
    if (open) $("[data-close-menu]", sidebar)?.focus();
    else if (restore) menu?.focus();
  }
  menu?.addEventListener("click", () => toggleMenu(!menuOpen));
  document
    .querySelectorAll("[data-close-menu]")
    .forEach((node) => node.addEventListener("click", () => toggleMenu(false)));
  smallScreen.addEventListener("change", () => toggleMenu(false, false));
  toggleMenu(false, false);
  document.addEventListener("keydown", (event) => {
    if (!menuOpen) return;
    if (event.key === "Escape") toggleMenu(false);
    if (event.key === "Tab") {
      const nodes = Array.from(sidebar.querySelectorAll("a,button")).filter(
        (node) => node.offsetParent !== null,
      );
      if (event.shiftKey && document.activeElement === nodes[0]) {
        event.preventDefault();
        nodes.at(-1).focus();
      } else if (!event.shiftKey && document.activeElement === nodes.at(-1)) {
        event.preventDefault();
        nodes[0].focus();
      }
    }
  });
  function dates(root = document) {
    try {
      const date = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        timeZone: "Asia/Tehran",
      });
      const time = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Tehran",
      });
      root.querySelectorAll("[data-persian-date]").forEach((node) => {
        node.textContent = date.format(
          new Date(`${node.dataset.persianDate}T12:00:00Z`),
        );
      });
      root.querySelectorAll("[data-persian-time]").forEach((node) => {
        node.textContent = time.format(new Date(node.dataset.persianTime));
      });
    } catch {
      /* Keep the server's readable date as fallback. */
    }
  }
  dates();

  // Sorting remains server-side, including all records across pagination.
  let tableRequest;
  document.addEventListener("click", async (event) => {
    const link = event.target.closest("[data-sort-link],[data-page-link]");
    if (
      !link ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      event.button !== 0
    )
      return;
    const region = link.closest("[data-table-region]");
    if (!region?.id || !window.fetch) return;
    event.preventDefault();
    tableRequest?.abort();
    const controller = new AbortController();
    tableRequest = controller;
    region.setAttribute("aria-busy", "true");
    region.classList.add("table-loading");
    const url = new URL(link.href, window.location.href);
    // Other tables may have changed since this region was rendered.
    if (link.hasAttribute("data-sort-link")) {
      const target = new URL(window.location.href);
      const prefix = link.dataset.sortPrefix || "";
      for (const key of [prefix + "sort", prefix + "dir"]) {
        target.searchParams.set(key, url.searchParams.get(key));
      }
      target.searchParams.delete("page");
      url.search = target.search;
    }
    try {
      const response = await fetch(url, {
        signal: controller.signal,
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("Table request failed");
      const doc = new DOMParser().parseFromString(
        await response.text(),
        "text/html",
      );
      const next = doc.getElementById(region.id);
      if (!next) throw new Error("Table region is missing");
      const scroll = $(".table-scroll", region)?.scrollLeft || 0;
      region.replaceWith(next);
      dates(next);
      next.classList.add("table-updated");
      const scrollNode = $(".table-scroll", next);
      if (scrollNode) scrollNode.scrollLeft = scroll;
      history.pushState({ studioTable: true }, "", url);
      for (const form of document.querySelectorAll(
        ".period-bar, .product-filters",
      )) {
        for (const key of ["sort", "dir"]) {
          if (!url.searchParams.has(key)) continue;
          let input = form.querySelector(`input[name="${key}"]`);
          if (!input) {
            input = document.createElement("input");
            input.type = "hidden";
            input.name = key;
            form.append(input);
          }
          input.value = url.searchParams.get(key);
        }
      }
      const focus = Array.from(next.querySelectorAll("[data-sort-link]")).find(
        (node) => node.dataset.sortKey === link.dataset.sortKey,
      );
      if (link.hasAttribute("data-sort-link"))
        focus?.focus({ preventScroll: true });
      else {
        next.setAttribute("tabindex", "-1");
        next.focus({ preventScroll: true });
        next.scrollIntoView({
          block: "start",
          behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "instant"
            : "smooth",
        });
      }
      announce("جدول به‌روزرسانی شد.");
    } catch (error) {
      if (error.name !== "AbortError") window.location.assign(url);
    } finally {
      region.removeAttribute("aria-busy");
      region.classList.remove("table-loading");
    }
  });
  window.addEventListener("popstate", () => window.location.reload());

  const photoDialog = $("#photo-dialog"),
    statusDialog = $("#status-dialog");
  let pendingStatus;
  document.addEventListener("click", (event) => {
    const photo = event.target.closest("[data-photo]");
    if (photo && photoDialog) {
      $("[data-dialog-photo]").src = photo.dataset.photo;
      $("[data-dialog-photo]").alt = photo.dataset.caption;
      $("[data-dialog-caption]").textContent = photo.dataset.caption;
      photoDialog.showModal();
    }
    if (event.target.closest("[data-close-dialog]"))
      event.target.closest("dialog")?.close();
    if (event.target.closest("[data-dismiss-flash]"))
      event.target.closest(".flash")?.remove();
  });
  document.querySelectorAll("dialog").forEach((dialog) =>
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        const r = dialog.getBoundingClientRect();
        if (
          event.clientX < r.left ||
          event.clientX > r.right ||
          event.clientY < r.top ||
          event.clientY > r.bottom
        )
          dialog.close();
      }
    }),
  );
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (form.matches(".status-form") && statusDialog) {
      event.preventDefault();
      const selected = $("select", form)?.selectedOptions[0];
      if (!selected?.value) return;
      pendingStatus = form;
      $("[data-status-description]").textContent =
        `فاکتور ${form.dataset.factor} با وضعیت «${selected.textContent}» ثبت شود؟`;
      statusDialog.showModal();
    } else if (form.matches("[data-editor-form]")) {
      const button = $("button[type=submit]", form);
      if (button) {
        button.disabled = true;
        button.textContent = "در حال ذخیره…";
      }
    }
  });
  $("[data-confirm-status]")?.addEventListener("click", (event) => {
    if (!pendingStatus) return;
    event.currentTarget.disabled = true;
    event.currentTarget.textContent = "در حال ثبت…";
    HTMLFormElement.prototype.submit.call(pendingStatus);
  });
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) window.location.reload();
  });

  const preview = $(".record-preview");
  if (preview) {
    const form = $("[data-editor-form]");
    const field = (name) => form?.elements.namedItem(name);
    const set = (key, value) => {
      const target = $(`[data-preview-${key}]`, preview);
      if (target) target.textContent = value || "—";
    };
    const label = (name) =>
      field(name)?.value ? field(name)?.selectedOptions?.[0]?.textContent : "";
    const render = () => {
      set("factor", field("factor_code")?.value.trim());
      set("florist", label("florist"));
      set("type", label("product_type"));
      const price = field("price")?.value;
      set(
        "price",
        price && Number(price) > 0 ? Number(price).toLocaleString("fa-IR") : "",
      );
      set("name", field("name")?.value || "نام فلوریست");
      set("code", field("code")?.value);
      set("active", field("is_active")?.checked ? "فعال" : "غیرفعال");
    };
    form?.addEventListener("input", render);
    form?.addEventListener("change", render);
    render();
    const fileField = field(
      preview.dataset.previewKind === "florist" ? "photo" : "image",
    );
    const clear = field(`${fileField?.name}-clear`),
      photo = $("[data-preview-photo]", preview),
      feedback = $("[data-upload-feedback]", preview);
    const initial = photo.cloneNode(true);
    let objectUrl;
    const restore = () => {
      photo.replaceChildren(...Array.from(initial.cloneNode(true).childNodes));
    };
    function updatePhoto() {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = undefined;
      const file = fileField?.files?.[0];
      if (!file) {
        if (clear?.checked) {
          photo.textContent = "عکس حذف می‌شود";
        } else restore();
        feedback.textContent = "";
        return;
      }
      feedback.textContent = file.name;
      objectUrl = URL.createObjectURL(file);
      const img = document.createElement("img");
      img.alt = "پیش‌نمایش تصویر انتخاب شده";
      img.src = objectUrl;
      img.addEventListener("error", () => {
        photo.textContent = "پیش‌نمایش این فرمت پس از ذخیره نمایش داده می‌شود.";
      });
      photo.replaceChildren(img);
    }
    fileField?.addEventListener("change", updatePhoto);
    clear?.addEventListener("change", updatePhoto);
    window.addEventListener("pagehide", () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    });
    $(".has-error input,.has-error select,.has-error textarea", form)?.focus();
  }

  const container = $("#trend-chart"),
    source = $("#trend-data");
  if (!container || !source) return;
  let series;
  try {
    series = JSON.parse(source.textContent);
  } catch {
    return;
  }
  const chartTable = $(".chart-data table");
  if (chartTable) {
    const rows = Array.from(chartTable.tBodies[0].rows).map((node, index) => ({
      node,
      ...series[index],
    }));
    const headers = Array.from(chartTable.tHead.rows[0].cells);
    headers.forEach((header, index) => {
      const key = ["label", "produced", "sold"][index];
      const label = header.textContent;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "sort-control";
      button.dataset.chartSort = key;
      const text = document.createElement("span");
      text.textContent = label;
      button.innerHTML =
        '<svg class="icon sort-icon" aria-hidden="true"><use href="#i-sort"/></svg>';
      button.prepend(text);
      header.replaceChildren(button);
      header.setAttribute("aria-sort", "none");
      button.addEventListener("click", () => {
        const descending = header.getAttribute("aria-sort") === "ascending";
        headers.forEach((cell) => {
          cell.setAttribute("aria-sort", "none");
          $("button", cell).classList.remove("is-sorted");
          $("svg", cell).classList.remove("sort-desc");
          $("use", cell).setAttribute("href", "#i-sort");
        });
        rows.sort(
          (a, b) =>
            (key === "label" ? a[key].localeCompare(b[key]) : a[key] - b[key]) *
            (descending ? -1 : 1),
        );
        chartTable.tBodies[0].append(...rows.map((row) => row.node));
        header.setAttribute(
          "aria-sort",
          descending ? "descending" : "ascending",
        );
        button.classList.add("is-sorted");
        $("svg", button).classList.toggle("sort-desc", descending);
        $("use", button).setAttribute("href", "#i-sort-active");
        announce(
          `${label} به ترتیب ${descending ? "کاهشی" : "افزایشی"} مرتب شد.`,
        );
      });
    });
  }
  if (!series.length || series.every((row) => !row.produced && !row.sold)) {
    container.innerHTML =
      '<div class="empty-state"><strong>هنوز روندی در این بازه نیست</strong><p>با ثبت محصول، نمودار اینجا نمایش داده می‌شود.</p></div>';
    return;
  }
  const shown = { produced: true, sold: true };
  const fmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
    month: "2-digit",
    day: "2-digit",
    timeZone: "Asia/Tehran",
  });
  const date = (iso) => fmt.format(new Date(`${iso}T12:00:00Z`));
  function draw() {
    const w = Math.max(260, container.clientWidth),
      h = 230,
      left = 27,
      right = 20,
      top = 18,
      bottom = 30;
    const ceil =
      Math.ceil(
        Math.max(
          4,
          ...series.flatMap((row) => [
            shown.produced ? row.produced : 0,
            shown.sold ? row.sold : 0,
          ]),
        ) / 4,
      ) * 4;
    const x = (i) =>
      left +
      (series.length === 1
        ? (w - left - right) / 2
        : (i * (w - left - right)) / (series.length - 1));
    const y = (v) => top + ((ceil - v) * (h - top - bottom)) / ceil;
    const points = (key) => series.map((row, i) => [x(i), y(row[key])]);
    const line = (coords) =>
      coords.map((p, i) => `${i ? "L" : "M"} ${p[0]} ${p[1]}`).join(" ");
    const axes = Array.from({ length: 5 }, (_, i) => {
      const value = ceil - (i * ceil) / 4;
      return `<path class="grid" d="M ${left} ${y(value)} H ${w - right}"/><text x="${left - 9}" y="${y(value) + 4}" text-anchor="end">${value.toLocaleString("fa-IR")}</text>`;
    }).join("");
    const step = Math.max(
      1,
      Math.ceil((series.length - 1) / (w < 440 ? 3 : 6)),
    );
    const labels = series
      .map((row, i) =>
        (i % step === 0 || i === series.length - 1) &&
        !(i !== series.length - 1 && i > series.length - 1 - step * 0.55)
          ? `<text x="${x(i)}" y="${h - 5}" text-anchor="middle">${date(row.label)}</text>`
          : "",
      )
      .join("");
    let traces = "";
    for (const key of ["produced", "sold"]) {
      if (!shown[key]) continue;
      const coords = points(key);
      if (key === "sold")
        traces += `<path class="area" d="${line(coords)} L ${coords.at(-1)[0]} ${h - bottom} L ${coords[0][0]} ${h - bottom} Z"/>`;
      traces += `<path class="line-${key}" d="${line(coords)}"/>`;
      traces += coords
        .map(
          (p, i) =>
            `<circle class="point" cx="${p[0]}" cy="${p[1]}" r="4" fill="${key === "produced" ? "#55745d" : "#bb6f78"}" data-index="${i}" tabindex="0" role="img" aria-label="${date(series[i].label)}، ${key === "produced" ? "تولید" : "فروش"} ${series[i][key]}"/>`,
        )
        .join("");
    }
    container.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="روند تعداد تولید و فروش"><defs><linearGradient id="sales-fill" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#cf8388" stop-opacity=".17"/><stop offset="1" stop-color="#cf8388" stop-opacity="0"/></linearGradient></defs>${axes}${labels}${traces}</svg><div class="chart-tooltip" role="status">برای بررسی یک روز، نقطهٔ آن را انتخاب کنید.</div>`;
  }
  function showPoint(target) {
    const row = series[Number(target.dataset.index)];
    if (row)
      $(".chart-tooltip", container).textContent =
        `${date(row.label)} · تولید ${row.produced.toLocaleString("fa-IR")} · فروش ${row.sold.toLocaleString("fa-IR")}`;
  }
  for (const type of ["pointerover", "click", "focusin"])
    container.addEventListener(type, (event) => {
      const dot = event.target.closest("[data-index]");
      if (dot) showPoint(dot);
    });
  document.querySelectorAll("[data-chart-series]").forEach((button) =>
    button.addEventListener("click", () => {
      const key = button.dataset.chartSeries;
      if (shown[key] && Object.values(shown).filter(Boolean).length === 1)
        return;
      shown[key] = !shown[key];
      button.setAttribute("aria-pressed", String(shown[key]));
      draw();
    }),
  );
  let width = 0;
  new ResizeObserver(() => {
    if (Math.abs(container.clientWidth - width) > 1) {
      width = container.clientWidth;
      draw();
    }
  }).observe(container);
  draw();
})();
