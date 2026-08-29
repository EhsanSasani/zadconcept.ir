(function () {
  "use strict";

  const persianDigits = "۰۱۲۳۴۵۶۷۸۹";
  const arabicDigits = "٠١٢٣٤٥٦٧٨٩";

  function normalizeDigits(value) {
    return String(value || "")
      .replace(/[۰-۹]/g, (digit) => String(persianDigits.indexOf(digit)))
      .replace(/[٠-٩]/g, (digit) => String(arabicDigits.indexOf(digit)))
      .replace(/[^0-9]/g, "");
  }

  function formatPrice(value) {
    const digits = normalizeDigits(value);
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, "/");
  }

  function digitCountBefore(value, position) {
    return normalizeDigits(value.slice(0, position)).length;
  }

  function caretForDigitCount(value, count) {
    if (!count) {
      return 0;
    }

    let digitsSeen = 0;
    for (let index = 0; index < value.length; index += 1) {
      if (/\d/.test(value[index])) {
        digitsSeen += 1;
      }
      if (digitsSeen === count) {
        return index + 1;
      }
    }
    return value.length;
  }

  function bindPriceInput(input) {
    input.addEventListener("input", () => {
      const caret = input.selectionStart || 0;
      const digitsBeforeCaret = digitCountBefore(input.value, caret);
      const formattedValue = formatPrice(input.value);

      if (input.value !== formattedValue) {
        input.value = formattedValue;
        const nextCaret = caretForDigitCount(formattedValue, digitsBeforeCaret);
        input.setSelectionRange(nextCaret, nextCaret);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document
      .querySelectorAll("[data-toman-price-input]")
      .forEach(bindPriceInput);
  });
})();
