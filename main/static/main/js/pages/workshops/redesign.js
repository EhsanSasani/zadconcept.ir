(() => {
  const form = document.getElementById("workshop-request-form");
  if (!form) return;

  const hiddenNote = document.getElementById("workshop-note-hidden");
  const participants = form.querySelector('[name="participant_count_ui"]');
  const noteInput = form.querySelector('[name="note_ui"]');

  const buildNote = () => {
    const selectedType = form.querySelector('[name="workshop_kind_ui"]:checked');
    const parts = [
      `نوع ورکشاپ: ${selectedType ? selectedType.value : "تجربه‌محور"}`,
    ];

    if (participants && participants.value.trim()) {
      parts.push(`تعداد نفرات تقریبی: ${participants.value.trim()}`);
    }

    if (noteInput && noteInput.value.trim()) {
      parts.push(`توضیحات: ${noteInput.value.trim()}`);
    }

    hiddenNote.value = parts.join(" | ");
  };

  form.addEventListener("submit", buildNote);
})();
