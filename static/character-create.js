const costs = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9};
const fixedGains = {6: 4, 8: 5, 10: 6, 12: 7};
const abilityNames = [
  "strength",
  "dexterity",
  "constitution",
  "intelligence",
  "wisdom",
  "charisma",
];
const form = document.getElementById("character-form");
const sections = [...form.querySelectorAll(".wizard-section")];
const draftKey = "dnd-manager-character-draft";
let currentStep = 0;

function draftFields() {
  return [...form.elements].filter(
    (field) =>
      field.name &&
      field.name !== "csrf_token" &&
      !["submit", "button"].includes(field.type),
  );
}

function saveDraft() {
  const values = {};
  for (const field of draftFields()) {
    values[field.name] = field.type === "checkbox" ? field.checked : field.value;
  }
  localStorage.setItem(draftKey, JSON.stringify({values, currentStep}));
}

function restoreDraft() {
  if (form.dataset.hasServerValues === "1") {
    return 0;
  }
  try {
    const draft = JSON.parse(localStorage.getItem(draftKey));
    if (!draft?.values) {
      return 0;
    }
    for (const field of draftFields()) {
      if (!(field.name in draft.values)) {
        continue;
      }
      if (field.type === "checkbox") {
        field.checked = Boolean(draft.values[field.name]);
      } else {
        field.value = draft.values[field.name];
      }
    }
    return Number(draft.currentStep) || 0;
  } catch {
    localStorage.removeItem(draftKey);
    return 0;
  }
}

const modifier = (score) => Math.floor((score - 10) / 2);
const signed = (value) => (value >= 0 ? `+${value}` : `${value}`);

function refreshPreview() {
  const scores = Object.fromEntries(
    abilityNames.map((name) => [
      name,
      Number(document.getElementById(name).value),
    ]),
  );
  const spent = abilityNames.reduce(
    (total, name) => total + (costs[scores[name]] ?? 99),
    0,
  );
  const status = document.getElementById("point-buy-status");
  status.querySelector("strong").textContent = spent;
  status.classList.toggle("is-valid", spent === 27);

  const classOption = document.getElementById("class_id").selectedOptions[0];
  const classBonuses = Object.fromEntries(
    abilityNames.map((name) => [
      name,
      Number(classOption?.dataset[`${name}Bonus`] || 0),
    ]),
  );
  const hitDie = Number(classOption?.dataset.hitDie);
  const racialBonuses = Object.fromEntries(
    abilityNames.map((name) => [name, 0]),
  );
  for (const name of abilityNames) {
    document.querySelector(`[data-modifier-for="${name}"]`).textContent =
      signed(
        modifier(
          scores[name] + classBonuses[name] + racialBonuses[name],
        ),
      );
  }
  const levelInput = document.getElementById("level");
  const level = levelInput ? Number(levelInput.value) : 1;
  const constitutionModifier = modifier(
    scores.constitution
      + classBonuses.constitution
      + racialBonuses.constitution,
  );
  if (fixedGains[hitDie]) {
    const firstLevel = Math.max(1, hitDie + constitutionModifier);
    const laterGain = Math.max(1, fixedGains[hitDie] + constitutionModifier);
    document.getElementById("hp-preview").textContent =
      firstLevel + (level - 1) * laterGain;
  } else {
    document.getElementById("hp-preview").textContent = "—";
  }

  document.getElementById("physical-preview").textContent =
    signed(
      modifier(
        scores.constitution
          + classBonuses.constitution
          + racialBonuses.constitution,
      ),
    );
  document.getElementById("elemental-preview").textContent =
    signed(
      modifier(
        scores.intelligence
          + classBonuses.intelligence
          + racialBonuses.intelligence,
      ),
    );
  document.getElementById("spiritual-preview").textContent =
    signed(
      modifier(
        scores.wisdom
          + classBonuses.wisdom
          + racialBonuses.wisdom,
      ),
    );
}

for (const field of [
  ...abilityNames,
  "class_id",
  "species_id",
  "level",
]) {
  document.getElementById(field)?.addEventListener("input", refreshPreview);
  document.getElementById(field)?.addEventListener("change", refreshPreview);
}


function showStep(index) {
  currentStep = Math.max(0, Math.min(index, sections.length - 1));
  sections.forEach((section, sectionIndex) => {
    section.hidden = sectionIndex !== currentStep;
  });
  sections[currentStep].scrollIntoView({behavior: "smooth", block: "start"});
  saveDraft();
}

function currentStepIsValid() {
  const fields = sections[currentStep].querySelectorAll(
    "input:not([type='hidden']), select, textarea",
  );
  for (const field of fields) {
    if (!field.reportValidity()) {
      return false;
    }
  }
  return true;
}

sections.forEach((section, index) => {
  const controls = document.createElement("div");
  controls.className = "wizard-controls";

  if (index > 0) {
    const previous = document.createElement("button");
    previous.type = "button";
    previous.className = "button-secondary";
    previous.textContent = "Étape précédente";
    previous.addEventListener("click", () => showStep(index - 1));
    controls.append(previous);
  }

  if (index < sections.length - 1) {
    const next = document.createElement("button");
    next.type = "button";
    next.textContent = "Étape suivante";
    next.addEventListener("click", () => {
      if (currentStepIsValid()) {
        showStep(index + 1);
      }
    });
    controls.append(next);
  }

  section.append(controls);
});

form.classList.add("wizard-enhanced");
const restoredStep = restoreDraft();
showStep(restoredStep);

form.addEventListener("invalid", (event) => {
  const invalidSection = event.target.closest(".wizard-section");
  const invalidIndex = sections.indexOf(invalidSection);
  if (invalidIndex >= 0 && invalidIndex !== currentStep) {
    showStep(invalidIndex);
  }
}, true);

form.addEventListener("submit", (event) => {
  const spent = abilityNames.reduce(
    (total, name) =>
      total + (costs[Number(document.getElementById(name).value)] ?? 99),
    0,
  );
  if (spent !== 27) {
    event.preventDefault();
    showStep(4);
  }
});

form.addEventListener("input", saveDraft);
form.addEventListener("change", saveDraft);

refreshPreview();
