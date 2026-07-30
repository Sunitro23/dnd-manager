const form = document.getElementById("admin-character-form");
const abilityNames = [
  "strength",
  "dexterity",
  "constitution",
  "intelligence",
  "wisdom",
  "charisma",
];
// Table de coûts, plage et gains de dé de vie fournis par le serveur :
// une seule source de vérité pour les règles, partagée avec Python.
const rules = JSON.parse(form.dataset.abilityRules);

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
  return abilityNames.reduce((total, name) => total + abilityCost(scores[name]), 0);
}

function abilityCost(score) {
  const cost = rules.costs[score];
  return cost === undefined ? Number.NaN : cost;
}

function previewHealth(scores) {
  const hitDie = Number(form.dataset.hitDie);
  const level = Number(document.getElementById("level").value);
  const constitutionModifier = modifier(effectiveConstitution(scores));
  return maximumHealth(hitDie, level, constitutionModifier);
}

function maximumHealth(hitDie, level, constitutionModifier) {
  const firstLevel = Math.max(1, hitDie + constitutionModifier);
  const laterGain = Math.max(1, rules.hit_die_gains[hitDie] + constitutionModifier);
  const newMaximum = firstLevel + (level - 1) * laterGain;
  return adjustedHealth(newMaximum);
}

function effectiveConstitution(scores) {
  return scores.constitution + constitutionBonus("classConstitutionBonus") +
    racialConstitutionBonus() + constitutionBonus("accessoryConstitutionBonus");
}

function constitutionBonus(name) {
  return Number(form.dataset[name] || 0);
}

function racialConstitutionBonus() {
  const unchanged = document.getElementById("species_id").value === form.dataset.originalSpeciesId;
  return unchanged ? constitutionBonus("racialConstitutionBonus") : 0;
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
  const budget = Number.isNaN(spent) ? "—" : spent;
  preview.textContent =
    `Budget : ${budget}/${rules.budget} · PV : ${health.currentHp}/${health.oldMaximum} → ` +
    `${health.newCurrent}/${health.newMaximum}`;
  preview.classList.toggle("is-valid", spent === rules.budget);
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
