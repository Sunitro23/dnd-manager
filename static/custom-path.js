(() => {
  function dialog() {
    return document.querySelector("[data-custom-path-dialog]");
  }

  function openEditor(trigger) {
    const editor = dialog();
    if (!editor) return;
    editor.querySelector("[data-custom-path-title]").textContent =
      `Modifier le rang ${trigger.dataset.customRank}`;
    const form = editor.querySelector("[data-custom-path-form]");
    form.action = trigger.dataset.customAction;
    const textarea = editor.querySelector("[data-custom-path-description]");
    textarea.value = trigger.dataset.customDescription || "";
    editor.showModal();
    textarea.focus();
  }

  document.addEventListener("click", (event) => {
    const close = event.target.closest("[data-custom-path-close]");
    if (close) {
      dialog()?.close();
      return;
    }
    const trigger = event.target.closest("[data-custom-rank-open]");
    if (!trigger || event.target.closest("form, button, a, input, textarea, select")) return;
    openEditor(trigger);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const trigger = event.target.closest("[data-custom-rank-open]");
    if (!trigger || event.target !== trigger) return;
    event.preventDefault();
    openEditor(trigger);
  });

  document.addEventListener("click", (event) => {
    const editor = dialog();
    if (editor && event.target === editor) editor.close();
  });
})();
