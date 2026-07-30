const abilityNames = [
  "strength", "dexterity", "constitution",
  "intelligence", "wisdom", "charisma",
];
const form = document.getElementById("character-form");
// Table de coûts et budget fournis par le serveur : une seule source de vérité.
const rules = JSON.parse(form.dataset.abilityRules);
const draftKey = "dnd-manager-character-draft";

const modifier = (score) => Math.floor((score - 10) / 2);
const signed = (value) => (value >= 0 ? `+${value}` : `${value}`);

function draftFields() {
  return [...form.elements].filter(
    (field) => field.name && field.name !== "csrf_token" &&
      !["submit", "button"].includes(field.type),
  );
}

function saveDraft() {
  const values = Object.fromEntries(draftFields().map((field) => [field.name, field.value]));
  localStorage.setItem(draftKey, JSON.stringify(values));
}

function restoreDraft() {
  if (form.dataset.hasServerValues === "1") return;
  const values = readDraft();
  if (values) applyDraft(values);
}

function readDraft() {
  try { return JSON.parse(localStorage.getItem(draftKey)); } catch {
    localStorage.removeItem(draftKey);
    return null;
  }
}

function applyDraft(values) {
  if (!values) return;
  for (const field of draftFields()) {
    if (field.name in values) field.value = values[field.name];
  }
}

function refresh() {
  abilityNames.forEach(refreshAbility);
  renderBudget(pointBuyTotal());
}

function refreshAbility(name) {
  const score = Number(document.getElementById(name).value);
  const total = score + classBonus(name);
  document.querySelector(`[data-modifier-for="${name}"]`).textContent =
    `${total} · ${signed(modifier(total))}`;
}

function classBonus(name) {
  const option = document.getElementById("class_id").selectedOptions[0];
  return Number(option?.dataset[`${name}Bonus`] || 0);
}

function pointBuyTotal() {
  return abilityNames.reduce(
    (total, name) => total + abilityCost(Number(document.getElementById(name).value)),
    0,
  );
}

function abilityCost(score) {
  const cost = rules.costs[score];
  return cost === undefined ? Number.NaN : cost;
}

function renderBudget(spent) {
  const status = document.getElementById("point-buy-status");
  status.querySelector("strong").textContent = Number.isNaN(spent) ? "—" : spent;
  status.classList.toggle("is-valid", spent === rules.budget);
}

restoreDraft();
form.addEventListener("input", refreshAndSave);
form.addEventListener("change", refreshAndSave);
form.addEventListener("submit", validateSubmission);

function refreshAndSave() {
  refresh();
  saveDraft();
}

function validateSubmission(event) {
  SUBMISSION_HANDLERS[pointBuyTotal() === 27](event);
}

function rejectSubmission(event) {
  event.preventDefault();
  document.getElementById("point-buy-status").scrollIntoView({behavior: "smooth"});
}

function acceptSubmission() {
  localStorage.removeItem(draftKey);
}

const SUBMISSION_HANDLERS = {true: acceptSubmission, false: rejectSubmission};
refresh();
