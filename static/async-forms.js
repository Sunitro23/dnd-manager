const SHEET_SELECTORS = [
  ".character-header", ".sheet-overview", ".progression-panel",
  ".inline-inventory",
];

document.addEventListener("submit", handleAsyncSubmission);

function handleAsyncSubmission(event) {
  if (event.defaultPrevented) return;
  const form = event.target.closest("[data-async-form]");
  if (!form) return;
  event.preventDefault();
  submitAsyncForm(form, event.submitter);
}

function submitAsyncForm(form, submitter) {
  const context = submissionContext(form, submitter);
  startSubmission(context);
  return performSubmission(form, context);
}

function performSubmission(form, context) {
  return requestForm(form, context.data)
    .then((result) => applyResult(result).then(() => showSaved(context.status, result)))
    .catch((error) => showError(context.status, error))
    .finally(() => setControlsDisabled(context.controls, false));
}

function submissionContext(form, submitter) {
  const data = new FormData(form);
  appendSubmitter(data, submitter);
  const controls = form.querySelectorAll("input, select, textarea, button");
  return {data, controls, status: document.querySelector(".save-status")};
}

function appendSubmitter(data, submitter) {
  if (submitter?.name && !data.has(submitter.name)) {
    data.append(submitter.name, submitter.value);
  }
}

function startSubmission(context) {
  setControlsDisabled(context.controls, true);
  if (!context.status) return;
  Object.assign(context.status, {hidden: false, className: "save-status",
                                 textContent: "Enregistrement…"});
}

function setControlsDisabled(controls, disabled) {
  controls.forEach((control) => { control.disabled = disabled; });
}

async function requestForm(form, data) {
  const url = new URL(form.getAttribute("action"), window.location.href);
  const response = await fetch(url, requestOptions(data));
  const result = parseResponse(await response.text(), response.status);
  if (!response.ok || !result.ok) throw new Error(result.message || "L’enregistrement a échoué.");
  return result;
}

function requestOptions(data) {
  return {method: "POST", body: data, headers: {"X-Requested-With": "XMLHttpRequest"}};
}

function parseResponse(text, status) {
  try { return JSON.parse(text); } catch {
    throw new Error(serverErrorMessage(text) || `Erreur serveur (${status}).`);
  }
}

function serverErrorMessage(text) {
  const page = new DOMParser().parseFromString(text, "text/html");
  return page.querySelector(".error-page p")?.textContent ||
    page.querySelector("title")?.textContent;
}

async function applyResult(result) {
  updateHealth(result);
  updateEstus(result);
  updateActionUses(result);
  updatePortrait(result);
  if (result.refresh_sheet) await refreshSheet(result);
  if (result.close_dialog) document.querySelector("[data-custom-path-dialog]")?.close();
}

function updateHealth(result) {
  if (result.current_hp === undefined) return;
  const hp = document.getElementById("current-hp");
  updateHealthElement(hp, result);
  document.querySelector(".hp-maximum").textContent = `Max ${result.max_hp}`;
}

function updateHealthElement(hp, result) {
  if (hp.matches("input")) {
    Object.assign(hp, {value: result.current_hp, max: result.max_hp});
  } else {
    hp.textContent = result.current_hp;
  }
}

function updateEstus(result) {
  if (result.estus_available === undefined) return;
  const selector = '.hp-popup input[name="action"][value="estus"]';
  const button = document.querySelector(selector)?.form?.querySelector("button");
  if (button) applyEstusState(button, result.estus_available);
}

function applyEstusState(button, available) {
  button.disabled = !available;
  button.querySelector("small").textContent = available ? "Soin complet" : "Déjà utilisé";
}

function updateActionUses(result) {
  if (!result.action_key) return;
  const selector = `[data-action-key="${CSS.escape(result.action_key)}"]`;
  const action = document.querySelector(selector);
  renderRemainingUses(action?.querySelector("[data-action-uses]"), result.remaining);
  disableSpentAction(action, result.remaining);
}

function disableSpentAction(action, remaining) {
  const button = action?.querySelector(".use-action");
  if (button) button.disabled = remaining === 0;
}

function renderRemainingUses(uses, remaining) {
  if (!uses) return;
  const total = uses.textContent.match(/\/(\d+)/)?.[1];
  uses.textContent = total ? `${remaining}/${total} restantes` :
    `${remaining} restante${remaining === 1 ? "" : "s"}`;
}

function updatePortrait(result) {
  if (!result.image_url) return;
  const portrait = document.createElement("img");
  portrait.src = `${result.image_url}?v=${Date.now()}`;
  portrait.alt = `Portrait de ${document.querySelector(".character-header h1").textContent}`;
  document.querySelector(".portrait-control").replaceChildren(portrait);
}

async function refreshSheet(result) {
  const page = await fetch(window.location.href);
  const copy = new DOMParser().parseFromString(await page.text(), "text/html");
  SHEET_SELECTORS.forEach((selector) => replaceSection(copy, selector));
  restoreSheetBehaviors();
  selectSavedItem(result.selected_item_id);
}

function replaceSection(copy, selector) {
  const current = document.querySelector(selector);
  const updated = copy.querySelector(selector);
  if (current && updated) current.replaceWith(updated);
}

function restoreSheetBehaviors() {
  syncSheetTabs();
  document.querySelectorAll("[data-item-fields]").forEach((fields) => {
    syncItemFields(fields.closest("form"));
  });
}

function selectSavedItem(itemId) {
  if (itemId === undefined) return;
  const browser = document.querySelector(".inventory-browser");
  if (browser) selectInventoryItem(browser, String(itemId));
}

function showSaved(status, result) {
  if (!status) return;
  status.classList.add("is-saved");
  status.textContent = result.message || "Enregistré.";
  window.setTimeout(() => { status.hidden = true; }, 2000);
}

function showError(status, error) {
  if (!status) return;
  status.classList.add("is-error");
  status.textContent = error.message;
}
