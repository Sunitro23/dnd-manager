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
  const scores = Object.fromEntries(
    abilityNames.map((name) => [name, Number(document.getElementById(name).value)]),
  );
  const spent = abilityNames.reduce(
    (total, name) => total + (costs[scores[name]] ?? 99),
    0,
  );
  const hitDie = Number(form.dataset.hitDie);
  const level = Number(document.getElementById("level").value);
  const constitutionModifier = modifier(
    scores.constitution
      + Number(form.dataset.classConstitutionBonus || 0)
      + (
        document.getElementById("species_id").value === form.dataset.originalSpeciesId
          ? Number(form.dataset.racialConstitutionBonus || 0)
          : 0
      ),
  );
  const firstLevel = Math.max(1, hitDie + constitutionModifier);
  const laterGain = Math.max(1, fixedGains[hitDie] + constitutionModifier);
  const newMaximum = firstLevel + (level - 1) * laterGain;
  const oldMaximum = Number(form.dataset.oldMaxHp);
  const currentHp = Number(form.dataset.currentHp);
  const newCurrent = currentHp === oldMaximum
    ? newMaximum
    : Math.min(currentHp, newMaximum);

  const preview = document.getElementById("admin-character-preview");
  preview.textContent =
    `Budget : ${spent}/27 · PV : ${currentHp}/${oldMaximum} → ${newCurrent}/${newMaximum}`;
  preview.classList.toggle("is-valid", spent === 27);
}

for (const field of [
  ...abilityNames,
  "level",
]) {
  document.getElementById(field).addEventListener("input", refreshAdminPreview);
}

refreshAdminPreview();

document.getElementById("species_id").addEventListener("change", refreshAdminPreview);
