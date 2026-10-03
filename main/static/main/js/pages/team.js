/* Authenticated workspace enhancement. No service worker or background uploads. */
(() => {
  "use strict";
  document.documentElement.classList.add("js");
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [
    ...root.querySelectorAll(selector),
  ];
  const user = document.body.dataset.teamUser;
  const draftKey = user ? `zad-team:${user}:product:v1` : null;
  let database,
    endingSession = false;
  let flushDraftWrites = () => Promise.resolve(),
    stopDraftTimer = () => {};
  function db() {
    if (!database)
      database = new Promise((resolve, reject) => {
        if (!window.indexedDB) return reject(new Error("storage unavailable"));
        const request = indexedDB.open("zad-team-drafts", 1);
        let finished = false;
        const fail = (error) => {
          finished = true;
          clearTimeout(timer);
          reject(error);
        };
        const timer = setTimeout(
          () => fail(new Error("storage timeout")),
          3000,
        );
        request.onupgradeneeded = () => {
          if (!request.result.objectStoreNames.contains("drafts"))
            request.result.createObjectStore("drafts");
        };
        request.onsuccess = () => {
          if (finished) {
            request.result.close();
            return;
          }
          finished = true;
          clearTimeout(timer);
          resolve(request.result);
        };
        request.onerror = () => fail(request.error);
        request.onblocked = () => fail(new Error("storage blocked"));
      });
    return database;
  }
  async function draftStore(action, value) {
    if (!draftKey) return;
    const connection = await db();
    return new Promise((resolve, reject) => {
      const transaction = connection.transaction(
        "drafts",
        action === "get" ? "readonly" : "readwrite",
      );
      const store = transaction.objectStore("drafts");
      const request =
        action === "put" ? store.put(value, draftKey) : store[action](draftKey);
      const timer = setTimeout(() => {
        try {
          transaction.abort();
        } catch (_) {
          /* Transaction may already be closed. */
        }
        reject(new Error("storage timeout"));
      }, 3000);
      transaction.oncomplete = () => {
        clearTimeout(timer);
        resolve(request.result);
      };
      transaction.onerror = () => {
        clearTimeout(timer);
        reject(transaction.error);
      };
      transaction.onabort = () => {
        clearTimeout(timer);
        reject(transaction.error);
      };
    });
  }
  $$("[data-team-logout]").forEach((form) =>
    form.addEventListener("submit", async (event) => {
      if (!draftKey) return;
      event.preventDefault();
      endingSession = true;
      stopDraftTimer();
      try {
        await flushDraftWrites();
        await draftStore("delete");
      } catch (_) {
        /* Session still ends if local storage is unavailable. */
      }
      HTMLFormElement.prototype.submit.call(form);
    }),
  );
  $$("[data-password-toggle]").forEach((button) =>
    button.addEventListener("click", () => {
      const input = $("input", button.parentElement);
      const visible = input.type === "password";
      input.type = visible ? "text" : "password";
      button.setAttribute("aria-pressed", String(visible));
      button.setAttribute(
        "aria-label",
        visible ? "پنهان کردن رمز عبور" : "نمایش رمز عبور",
      );
    }),
  );
  const dialog = $("[data-photo-dialog]");
  if (dialog && typeof dialog.showModal === "function") {
    $$("[data-zoom-photo]").forEach((link) =>
      link.addEventListener("click", (event) => {
        event.preventDefault();
        $("[data-dialog-image]").src = link.dataset.zoomPhoto;
        $("[data-dialog-image]").alt = link.dataset.photoCaption || "";
        $("[data-dialog-caption]").textContent =
          link.dataset.photoCaption || "";
        dialog.showModal();
      }),
    );
    $("[data-close-photo]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  }
  const profile = $("[data-profile-form]");
  if (profile) {
    const input = $("input[type=file]", profile);
    let profileURL;
    input?.addEventListener("change", () => {
      const file = input.files[0];
      if (!file) return;
      if (profileURL) URL.revokeObjectURL(profileURL);
      const preview = $("[data-profile-preview]");
      profileURL = URL.createObjectURL(file);
      preview.onload = () => {
        preview.hidden = false;
        const initial = $("[data-profile-initial]");
        if (initial) initial.hidden = true;
      };
      preview.onerror = () => {
        preview.hidden = true;
      };
      preview.src = profileURL;
    });
  }
  const form = $("[data-product-form]");
  if (
    !form ||
    !window.FormData ||
    !window.XMLHttpRequest ||
    !window.URL?.createObjectURL
  )
    return;
  const imageInput = $("[data-product-image]", form);
  const cameraInput = $("[data-camera-input]", form);
  const preview = $("[data-photo-preview]");
  const draftState = $("[data-draft-state]");
  const errorBox = $("[data-form-errors]");
  const submitLabel = $("[data-submit-label]");
  const status = $("[data-upload-state]");
  const progress = $("[data-upload-progress]");
  const banner = $("[data-draft-banner]");
  const fieldNames = [
    "submission_key",
    "florist",
    "production_type",
    "product_type",
    "price",
    "factor_code",
    "notes",
  ];
  let selectedFile = imageInput.files[0] || null;
  let objectURL,
    saveTimer,
    request,
    savedDraft,
    acknowledged = false,
    restoring = false;
  let submitting = false,
    draftReady = false,
    draftPersisted = false,
    csrfRefreshRequired = false;
  let lockedFields = [];
  // Writes are serialized so a late save cannot recreate a successfully cleared draft.
  let writeQueue = Promise.resolve();
  flushDraftWrites = () => writeQueue;
  stopDraftTimer = () => clearTimeout(saveTimer);
  function lockFields() {
    lockedFields = $$("input, select, textarea, button", form).filter(
      (field) => !field.disabled && !field.matches("[data-cancel-upload]"),
    );
    lockedFields.forEach((field) => {
      field.disabled = true;
    });
  }
  function unlockFields() {
    lockedFields.forEach((field) => {
      field.disabled = false;
    });
    lockedFields = [];
  }
  const normalizeDigits = (text) =>
    String(text)
      .replace(/[۰-۹]/g, (c) => "۰۱۲۳۴۵۶۷۸۹".indexOf(c))
      .replace(/[٠-٩]/g, (c) => "٠١٢٣٤٥٦٧٨٩".indexOf(c));
  function formatPriceInput() {
    const input = form.elements.price;
    const original = input.value;
    const digits = (value) => normalizeDigits(value).replace(/[^0-9]/g, "");
    const formatted = digits(original).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    if (original === formatted) return;
    const start = input.selectionStart;
    const end = input.selectionEnd;
    const direction = input.selectionDirection;
    input.value = formatted;
    if (document.activeElement === input && start !== null && end !== null) {
      const position = (count) => {
        if (!count) return 0;
        let seen = 0;
        for (let i = 0; i < formatted.length; i++) {
          if (/[0-9]/.test(formatted[i]) && ++seen === count) return i + 1;
        }
        return formatted.length;
      };
      input.setSelectionRange(
        position(digits(original.slice(0, start)).length),
        position(digits(original.slice(0, end)).length),
        direction,
      );
    }
  }
  function updateCopy() {
    const productionType = form.elements.production_type.value;
    const copy = $("[data-publish-copy]");
    if (productionType === "CUSTOM") {
      copy.textContent = "در کارنامه فلوریست ثبت می‌شود؛ عکس، قیمت و شماره فاکتور به گروه سفارشی‌ها می‌رود.";
      if (!submitting) submitLabel.textContent = "ثبت سفارش اختصاصی";
    } else if (productionType === "DAILY") {
      copy.textContent = "در سایت منتشر می‌شود؛ عکس، قیمت و شماره فاکتور به گروه آماده‌ها می‌رود.";
      if (!submitting) submitLabel.textContent = "ثبت و انتشار محصول";
    } else {
      copy.textContent = "برای ادامه، محل استفاده محصول را انتخاب کنید.";
      if (!submitting) submitLabel.textContent = "ثبت محصول";
    }
    const amount = normalizeDigits(form.elements.price.value).replace(
      /[,٬\s]/g,
      "",
    );
    $("[data-price-readout]").textContent =
      /^\d+$/.test(amount) && Number(amount) > 0
        ? `${Number(amount).toLocaleString("fa-IR")} تومان`
        : "";
  }
  function showPhoto(file) {
    selectedFile = file;
    $("[data-photo-picker]").classList.toggle("has-photo", !!file);
    if (objectURL) URL.revokeObjectURL(objectURL);
    preview.hidden = true;
    $("[data-preview-unavailable]").hidden = true;
    $("[data-photo-empty]").hidden = !!file;
    $("[data-photo-selected]").hidden = !file;
    $("[data-gallery-label]").textContent = file ? "تعویض عکس" : "از گالری";
    imageInput.required = !file;
    if (!file) return;
    objectURL = URL.createObjectURL(file);
    preview.onload = () => {
      preview.hidden = false;
      $("[data-preview-unavailable]").hidden = true;
    };
    preview.onerror = () => {
      preview.hidden = true;
      $("[data-preview-unavailable]").hidden = false;
    };
    preview.src = objectURL;
  }
  function snapshot() {
    const fields = {};
    fieldNames.forEach((name) => {
      fields[name] = form.elements[name].value;
    });
    return { fields, image: selectedFile, savedAt: Date.now() };
  }
  function saveDraft() {
    clearTimeout(saveTimer);
    if (acknowledged || endingSession || restoring || !draftKey)
      return writeQueue;
    const value = snapshot();
    writeQueue = writeQueue
      .catch(() => {})
      .then(async () => {
        if (acknowledged || endingSession) return;
        try {
          await draftStore("put", value);
          draftPersisted = true;
          draftState.textContent = "پیش‌نویس روی همین دستگاه ذخیره شد.";
        } catch (_) {
          draftPersisted = false;
          draftState.textContent =
            "ذخیره روی دستگاه ممکن نیست؛ تا پایان ثبت، صفحه را باز نگه دارید.";
        }
      });
    return writeQueue;
  }
  function scheduleSave() {
    if (savedDraft && !banner.hidden) return;
    draftPersisted = false;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 350);
  }
  function clearErrors() {
    errorBox.replaceChildren();
    errorBox.classList.add("empty");
    $$("[data-field-errors]", form).forEach((node) => node.replaceChildren());
    $$("[aria-invalid]", form).forEach((node) =>
      node.removeAttribute("aria-invalid"),
    );
  }
  function showError(message, errors, loginURL) {
    clearErrors();
    const paragraph = document.createElement("p");
    paragraph.textContent = message;
    errorBox.append(paragraph);
    if (errors)
      Object.entries(errors).forEach(([name, messages]) => {
        const target = $$("[data-field-errors]", form).find(
          (node) => node.dataset.fieldErrors === name,
        );
        (Array.isArray(messages) ? messages : [messages]).forEach((text) => {
          const line = document.createElement("p");
          line.textContent = String(text);
          (target || errorBox).append(line);
        });
        const field = form.elements[name];
        if (field && typeof field.setAttribute === "function")
          field.setAttribute("aria-invalid", "true");
      });
    if (loginURL) {
      const link = document.createElement("a");
      link.textContent = "ورود دوباره به حساب";
      link.className = "button button-secondary";
      link.href = `/studio/login/?next=${encodeURIComponent(location.pathname)}`;
      if (!draftPersisted) {
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = "ورود در پنجره تازه";
      }
      errorBox.append(link);
    }
    errorBox.classList.remove("empty");
    errorBox.focus();
  }
  function finishFailure(message, errors, loginURL) {
    request = null;
    submitting = false;
    unlockFields();
    form.removeAttribute("aria-busy");
    $("[data-cancel-upload]").hidden = true;
    $("[data-upload-label]").textContent = "ثبت نهایی تأیید نشده است";
    $("[data-upload-help]").textContent = draftPersisted
      ? "عکس و اطلاعات روی همین دستگاه ذخیره شده‌اند. با همین پیش‌نویس دوباره تلاش کنید."
      : "عکس و اطلاعات در همین صفحه باقی‌اند؛ صفحه را نبندید و برای ثبت دوباره تلاش کنید.";
    submitLabel.textContent = "تلاش دوباره برای ثبت";
    showError(message, errors, loginURL);
  }
  function refreshCsrf() {
    return new Promise((resolve, reject) => {
      const refresh = new XMLHttpRequest();
      request = refresh;
      refresh.open("GET", form.action || location.href);
      refresh.timeout = 15000;
      refresh.onload = () => {
        request = null;
        const page = new DOMParser().parseFromString(
          refresh.responseText,
          "text/html",
        );
        const token = $(
          "[data-product-form] input[name=csrfmiddlewaretoken]",
          page,
        );
        if (refresh.status === 200 && token?.value) {
          form.elements.csrfmiddlewaretoken.value = token.value;
          csrfRefreshRequired = false;
          resolve();
        } else reject(new Error("session unavailable"));
      };
      refresh.onerror =
        refresh.ontimeout =
        refresh.onabort =
          () => {
            request = null;
            reject(new Error("session unavailable"));
          };
      refresh.send();
    });
  }
  $("[data-open-camera]").addEventListener("click", () => cameraInput.click());
  $("[data-open-gallery]").addEventListener("click", () => imageInput.click());
  $("[data-photo-empty]").addEventListener("click", () => imageInput.click());
  [imageInput, cameraInput].forEach((input) =>
    input.addEventListener("change", () => {
      if (!input.files[0]) return;
      showPhoto(input.files[0]);
      if (input === cameraInput) {
        try {
          const transfer = new DataTransfer();
          transfer.items.add(selectedFile);
          imageInput.files = transfer.files;
        } catch (_) {
          /* FormData below carries the selected camera file. */
        }
      }
      scheduleSave();
    }),
  );
  $("[data-remove-photo]").addEventListener("click", () => {
    imageInput.value = "";
    cameraInput.value = "";
    showPhoto(null);
    scheduleSave();
  });
  form.addEventListener("input", (event) => {
    if (event.target === form.elements.price) formatPriceInput();
    updateCopy();
    scheduleSave();
  });
  form.addEventListener("change", () => {
    updateCopy();
    scheduleSave();
  });
  $("[data-restore-draft]").addEventListener("click", () => {
    if (!savedDraft) return;
    restoring = true;
    // Drafts saved before maker selection was added must ask for a maker.
    form.elements.florist.value = "";
    fieldNames.forEach((name) => {
      if (savedDraft.fields[name] !== undefined)
        form.elements[name].value = savedDraft.fields[name];
    });
    showPhoto(savedDraft.image || null);
    if (selectedFile) {
      try {
        const transfer = new DataTransfer();
        transfer.items.add(selectedFile);
        imageInput.files = transfer.files;
      } catch (_) {
        /* Upload uses preserved Blob. */
      }
    }
    banner.hidden = true;
    restoring = false;
    savedDraft = null;
    draftPersisted = true;
    formatPriceInput();
    updateCopy();
    draftState.textContent = selectedFile
      ? "عکس و اطلاعات پیش‌نویس بازیابی شد."
      : "اطلاعات بازیابی شد؛ عکس محصول را انتخاب کنید.";
  });
  $("[data-discard-draft]").addEventListener("click", async () => {
    savedDraft = null;
    banner.hidden = true;
    try {
      await draftStore("delete");
      draftState.textContent = "برای ثبت یک محصول تازه آماده‌اید.";
    } catch (_) {
      draftState.textContent =
        "پاک‌کردن پیش‌نویس ممکن نشد؛ ذخیره دستگاه در دسترس نیست.";
    }
    scheduleSave();
  });
  $("[data-cancel-upload]").addEventListener("click", () => request?.abort());
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitting) return;
    if (!draftReady) {
      showError("پیش‌نویس دستگاه در حال بررسی است؛ کمی صبر کنید.");
      return;
    }
    if (savedDraft && !banner.hidden) {
      showError("ابتدا ادامه پیش‌نویس یا شروع تازه را انتخاب کنید.");
      return;
    }
    if (!selectedFile) {
      showError("یک عکس برای محصول انتخاب کنید.", {
        image: ["عکس محصول ضروری است."],
      });
      return;
    }
    if (!form.reportValidity()) return;
    clearErrors();
    submitting = true;
    const body = new FormData(form);
    body.set("image", selectedFile, selectedFile.name || "product.jpg");
    lockFields();
    status.hidden = false;
    form.setAttribute("aria-busy", "true");
    $("[data-upload-label]").textContent = "در حال آماده‌سازی ثبت…";
    $("[data-upload-help]").textContent =
      "تا پایان ثبت، این صفحه را باز نگه دارید.";
    $("[data-cancel-upload]").hidden = true;
    submitLabel.textContent = "در حال ثبت…";
    await saveDraft();
    if (csrfRefreshRequired) {
      $("[data-upload-label]").textContent = "در حال بررسی نشست…";
      $("[data-cancel-upload]").hidden = false;
      try {
        await refreshCsrf();
        body.set(
          "csrfmiddlewaretoken",
          form.elements.csrfmiddlewaretoken.value,
        );
      } catch (_) {
        finishFailure(
          "نشست آماده ثبت نیست. در حساب وارد شوید و از همین صفحه دوباره تلاش کنید.",
          null,
          true,
        );
        return;
      }
    }
    const xhr = new XMLHttpRequest();
    request = xhr;
    xhr.open("POST", form.action || location.href);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    xhr.timeout = 180000;
    progress.value = 0;
    $("[data-upload-percent]").textContent = "";
    $("[data-upload-label]").textContent = "در حال فرستادن عکس…";
    $("[data-upload-help]").textContent =
      "تا پایان ثبت، این صفحه را باز نگه دارید.";
    $("[data-cancel-upload]").hidden = false;
    submitLabel.textContent = "در حال ثبت…";
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) {
        progress.removeAttribute("value");
        return;
      }
      const percentage = Math.round((event.loaded / event.total) * 100);
      progress.value = percentage;
      $("[data-upload-percent]").textContent =
        `${percentage.toLocaleString("fa-IR")}٪`;
      if (percentage === 100)
        $("[data-upload-label]").textContent = "عکس رسید؛ در انتظار تأیید ثبت…";
    };
    xhr.onload = async () => {
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch (_) {
        data = null;
      }
      if (
        xhr.status >= 200 &&
        xhr.status < 300 &&
        data?.ok === true &&
        data.record_id &&
        data.redirect_url
      ) {
        acknowledged = true;
        clearTimeout(saveTimer);
        request = null;
        $("[data-upload-label]").textContent = data.message || "محصول ثبت شد.";
        await writeQueue;
        try {
          await draftStore("delete");
        } catch (_) {
          /* The server UUID makes any recovered retry idempotent. */
        }
        const destination = new URL(data.redirect_url, location.origin);
        if (destination.origin === location.origin)
          location.assign(destination.href);
        else location.assign(`/team/products/${data.record_id}/`);
        return;
      }
      if (xhr.status === 401 || xhr.status === 403) csrfRefreshRequired = true;
      const message =
        xhr.status === 401
          ? "نشست شما پایان یافته است. وارد شوید و همین پیش‌نویس را ادامه دهید."
          : xhr.status === 403
            ? "مجوز ثبت یا نشست مرورگر نیاز به بررسی دارد. با تلاش دوباره نشست بررسی می‌شود؛ اگر خطا ادامه داشت، دوباره وارد شوید."
            : data?.errors
              ? "این موارد را بررسی کنید و دوباره ثبت کنید."
              : "تأیید ثبت دریافت نشد. اتصال را بررسی کنید و دوباره تلاش کنید.";
      finishFailure(
        message,
        data?.errors,
        xhr.status === 401 || xhr.status === 403,
      );
    };
    xhr.onerror = () =>
      finishFailure(
        "ارتباط قطع شد. پس از اتصال، با همین پیش‌نویس دوباره ثبت کنید.",
      );
    xhr.ontimeout = () =>
      finishFailure(
        "پاسخ سرور دیر شد. با همین پیش‌نویس دوباره تلاش کنید تا ثبت تکراری نشود.",
      );
    xhr.onabort = () =>
      finishFailure(
        "ارسال متوقف شد. ممکن است درخواست به سرور رسیده باشد؛ برای بررسی و ادامه، همین پیش‌نویس را دوباره ثبت کنید.",
      );
    try {
      xhr.send(body);
    } catch (_) {
      finishFailure("ارسال آغاز نشد. اتصال را بررسی کنید و دوباره تلاش کنید.");
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden" && banner.hidden) saveDraft();
  });
  window.addEventListener("beforeunload", (event) => {
    if (submitting && !acknowledged) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  formatPriceInput();
  updateCopy();
  form.noValidate = true;
  document.documentElement.classList.add("product-enhanced");
  draftStore("get")
    .then((value) => {
      if (value?.fields?.submission_key) {
        savedDraft = value;
        banner.hidden = false;
      }
    })
    .catch(() => {
      draftState.textContent =
        "ذخیره پیش‌نویس در این مرورگر در دسترس نیست؛ صفحه را باز نگه دارید.";
    })
    .finally(() => {
      draftReady = true;
    });
})();
