(() => {
  const menu = document.querySelector("[data-menu]");
  const sidebar = document.querySelector(".studio-sidebar");
  const backdrop = document.querySelector("[data-close-menu]");
  function toggle(open) {
    sidebar?.classList.toggle("open", open);
    if (backdrop) backdrop.hidden = !open;
    menu?.setAttribute("aria-expanded", String(open));
    document.body.style.overflow = open ? "hidden" : "";
  }
  menu?.addEventListener("click", () =>
    toggle(!sidebar.classList.contains("open")),
  );
  backdrop?.addEventListener("click", () => toggle(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") toggle(false);
  });
  document.querySelectorAll(".status-form").forEach((form) =>
    form.addEventListener("submit", (event) => {
      const selection = form.querySelector("select");
      if (
        !selection?.value ||
        !window.confirm(
          `وضعیت فاکتور را به «${selection.selectedOptions[0].textContent}» تغییر می‌دهید؟`,
        )
      ) {
        event.preventDefault();
      }
    }),
  );
  try {
    const dateFmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
    const timeFmt = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
    document.querySelectorAll("[data-persian-date]").forEach((node) => {
      node.textContent = dateFmt.format(
        new Date(`${node.dataset.persianDate}T12:00:00`),
      );
    });
    document.querySelectorAll("[data-persian-time]").forEach((node) => {
      node.textContent = timeFmt.format(new Date(node.dataset.persianTime));
    });
  } catch {
    /* Server rendered date remains readable. */
  }

  const preview = document.querySelector(".record-preview");
  if (preview) {
    const form = document.querySelector(".form-panel form");
    const field = (name) => form?.querySelector(`[name="${name}"]`);
    const set = (key, value) => {
      const node = preview.querySelector(`[data-preview-${key}]`);
      if (node) node.textContent = value || "—";
    };
    const selected = (name) => {
      const control = field(name);
      return control?.selectedOptions?.[0]?.value
        ? control.selectedOptions[0].textContent.trim()
        : "";
    };
    const render = () => {
      set("factor", field("factor_code")?.value.trim());
      set("florist", selected("florist"));
      set("type", selected("product_type"));
      const price = field("price")?.value;
      set("price", price && Number(price) > 0 ? Number(price).toLocaleString("fa-IR") : "");
    };
    form?.addEventListener("input", render);
    form?.addEventListener("change", render);
    render();
    const imageField = field("image");
    const photo = preview.querySelector("[data-preview-photo]");
    let objectUrl;
    imageField?.addEventListener("change", () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = undefined;
      const file = imageField.files?.[0];
      if (!file) return;
      photo.replaceChildren();
      if (file.type.startsWith("image/")) {
        objectUrl = URL.createObjectURL(file);
        const image = document.createElement("img");
        image.src = objectUrl;
        image.alt = "پیش‌نمایش تصویر انتخاب شده";
        photo.append(image);
      } else {
        photo.textContent = `تصویر انتخاب شد: ${file.name}`;
      }
    });
    window.addEventListener("pagehide", () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    });
  }

  const container = document.querySelector("#trend-chart");
  const source = document.querySelector("#trend-data");
  if (!container || !source) return;
  let series;
  try {
    series = JSON.parse(source.textContent);
  } catch {
    return;
  }
  const shortDate = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
    month: "2-digit",
    day: "2-digit",
  });
  const displayDate = (iso) => shortDate.format(new Date(`${iso}T12:00:00`));
  if (!series.length || series.every((row) => !row.produced && !row.sold)) {
    container.innerHTML =
      '<div class="empty-state"><strong>هنوز روندی برای این بازه وجود ندارد</strong><p>با ثبت اولین محصول، نمودار نمایش داده می‌شود.</p></div>';
    return;
  }
  const w = 720,
    h = 174,
    left = 31,
    right = 18,
    top = 12,
    bottom = 29;
  const max = Math.max(4, ...series.flatMap((row) => [row.produced, row.sold]));
  const ceil = Math.ceil(max / 4) * 4;
  const x = (i) =>
    left +
    (series.length === 1
      ? (w - left - right) / 2
      : (i * (w - left - right)) / (series.length - 1));
  const y = (value) => top + ((ceil - value) * (h - top - bottom)) / ceil;
  const points = (key) => series.map((row, i) => [x(i), y(row[key])]);
  // Straight segments preserve the recorded values without smoothing peaks.
  const line = (coords) =>
    coords.map((p, i) => `${i ? "L" : "M"} ${p[0]} ${p[1]}`).join(" ");
  const produced = points("produced"),
    sold = points("sold");
  const area = `${line(sold)} L ${sold.at(-1)[0]} ${h - bottom} L ${sold[0][0]} ${h - bottom} Z`;
  const axes = Array.from({ length: 5 }, (_, i) => {
    const value = ceil - (i * ceil) / 4;
    const pos = y(value);
    return `<path class="grid" d="M ${left} ${pos} H ${w - right}"/><text x="${left - 9}" y="${pos + 3}" text-anchor="end">${value.toLocaleString("fa-IR")}</text>`;
  }).join("");
  const step = Math.max(1, Math.ceil(series.length / 7));
  const labels = series
    .map((row, i) =>
      i % step === 0 || i === series.length - 1
        ? `<text x="${x(i)}" y="${h - 5}" text-anchor="middle">${displayDate(row.label)}</text>`
        : "",
    )
    .join("");
  const circles = (coords, key, color) =>
    coords
      .map(
        (p, i) =>
          `<circle class="point" cx="${p[0]}" cy="${p[1]}" r="3.8" fill="${color}" tabindex="0" role="img" aria-label="${displayDate(series[i].label)}، ${key === "produced" ? "تولید" : "فروش"} ${series[i][key]}" data-index="${i}"/>`,
      )
      .join("");
  container.innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="false"><defs><linearGradient id="sales-fill" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#e8a8a4" stop-opacity=".25"/><stop offset="1" stop-color="#e8a8a4" stop-opacity="0"/></linearGradient></defs>${axes}${labels}<path class="area" d="${area}"/><path class="line-produced" d="${line(produced)}"/><path class="line-sold" d="${line(sold)}"/>${circles(produced, "produced", "#71886a")}${circles(sold, "sold", "#e4a19e")}</svg>`;
  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  tooltip.hidden = true;
  container.append(tooltip);
  function show(target) {
    const row = series[Number(target.dataset.index)];
    if (!row) return;
    tooltip.textContent = `${displayDate(row.label)} · تولید ${row.produced.toLocaleString("fa-IR")} · فروش ${row.sold.toLocaleString("fa-IR")}`;
    tooltip.hidden = false;
    const box = container.getBoundingClientRect();
    const dot = target.getBoundingClientRect();
    tooltip.style.left = `${Math.max(0, Math.min(box.width - tooltip.offsetWidth, dot.left - box.left - tooltip.offsetWidth / 2))}px`;
    tooltip.style.top = `${Math.max(0, dot.top - box.top - 42)}px`;
  }
  container.addEventListener("pointerover", (event) => {
    const dot = event.target.closest("[data-index]");
    if (dot) show(dot);
  });
  container.addEventListener("pointerout", (event) => {
    if (event.target.closest("[data-index]")) tooltip.hidden = true;
  });
  container.addEventListener("focusin", (event) => {
    const dot = event.target.closest("[data-index]");
    if (dot) show(dot);
  });
  container.addEventListener("focusout", () => {
    tooltip.hidden = true;
  });
})();
