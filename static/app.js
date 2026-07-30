document.addEventListener("submit", confirmSubmission);

function confirmSubmission(event) {
  const message = event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
}

function clearCreatedDraft() {
  const currentUrl = new URL(window.location.href);
  if (currentUrl.searchParams.get("created") !== "1") return;
  localStorage.removeItem("dnd-manager-character-draft");
  currentUrl.searchParams.delete("created");
  window.history.replaceState({}, "", currentUrl);
}

clearCreatedDraft();

function syncItemFields(form) {
  const type = form.querySelector('[name="item_type"]')?.value;
  form.querySelectorAll("[data-fields-for]").forEach((group) => {
    group.hidden = !group.dataset.fieldsFor.split(" ").includes(type);
  });
}

function initializeItemFields(fields) {
  syncItemFields(fields.closest("form"));
}

function handleFieldChange(event) {
  if (event.target.matches('[name="item_type"]')) syncItemFields(event.target.form);
  const field = event.target.closest("[data-submit-on-change]");
  if (field?.checkValidity()) field.form.requestSubmit();
}

document.querySelectorAll("[data-item-fields]").forEach(initializeItemFields);
document.addEventListener("change", handleFieldChange);
