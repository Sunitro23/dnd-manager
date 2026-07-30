const form = document.getElementById("admin-character-form");
const abilityNames = [
  "strength",
  "dexterity",
  "constitution",
  "intelligence",
  "wisdom",
  "charisma",
];
const costs = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9};
const fixedGains = {6: 4, 8: 5, 10: 6, 12: 7};

function modifier(score) {
  return Math.floor((score - 10) / 2);
}

function refreshAdminPreview() {
  const scores = abilityScores();
  const spent = pointBuyTotal(scores);
  const health = previewHealth(scores);
  renderPreview(spent, health);
}

function abilityScores() {
  return Object.fromEntries(
    abilityNames.map((name) => [name, Number(document.getElementById(name).value)]),
  );
}

function pointBuyTotal(scores) {
  return abilityNames.reduce((total, name) => total + (costs[scores[name]] ?? 99), 0);
}

function previewHealth(scores) {
  const hitDie = Number(form.dataset.hitDie);
  const level = Number(document.getElementById("level").value);
  const constitutionModifier = modifier(effectiveConstitution(scores));
  return maximumHealth(hitDie, level, constitutionModifier);
}

function maximumHealth(hitDie, level, constitutionModifier) {
  const firstLevel = Math.max(1, hitDie + constitutionModifier);
  const laterGain = Math.max(1, fixedGains[hitDie] + constitutionModifier);
  const newMaximum = firstLevel + (level - 1) * laterGain;
  return adjustedHealth(newMaximum);
}

function effectiveConstitution(scores) {
  const classBonus = Number(form.dataset.classConstitutionBonus || 0);
  return scores.constitution + classBonus + racialConstitutionBonus();
}

function racialConstitutionBonus() {
  const unchanged = document.getElementById("species_id").value === form.dataset.originalSpeciesId;
  return unchanged ? Number(form.dataset.racialConstitutionBonus || 0) : 0;
}

function adjustedHealth(newMaximum) {
  const oldMaximum = Number(form.dataset.oldMaxHp);
  const currentHp = Number(form.dataset.currentHp);
  const newCurrent = adjustedCurrent(currentHp, oldMaximum, newMaximum);
  return {currentHp, oldMaximum, newCurrent, newMaximum};
}

function adjustedCurrent(current, oldMaximum, newMaximum) {
  return current === oldMaximum ? newMaximum : Math.min(current, newMaximum);
}

function renderPreview(spent, health) {
  const preview = document.getElementById("admin-character-preview");
  preview.textContent =
    `Budget : ${spent}/27 · PV : ${health.currentHp}/${health.oldMaximum} → ` +
    `${health.newCurrent}/${health.newMaximum}`;
  preview.classList.toggle("is-valid", spent === 27);
}

function bindPreviewFields() {
  for (const field of [...abilityNames, "level"]) bindPreviewField(field);
}

function bindPreviewField(field) {
  document.getElementById(field).addEventListener("input", refreshAdminPreview);
}

bindPreviewFields();
refreshAdminPreview();

document.getElementById("species_id").addEventListener("change", refreshAdminPreview);
