const normalizedEditor = document.querySelector("[data-normalized-capability-editor]");

if (normalizedEditor) {
  const list = normalizedEditor.querySelector("[data-normalized-operation-list]");
  const counter = normalizedEditor.querySelector("[data-operation-count]");
  const template = document.querySelector("#normalized-operation-template");

  function enabledField(operation, suffix) {
    return [...operation.querySelectorAll(`[name$="_${suffix}"]`)]
      .find((field) => !field.disabled);
  }

  function fieldValue(operation, suffix) {
    return enabledField(operation, suffix)?.value || "";
  }

  function effectPreview(operation) {
    const type = fieldValue(operation, "type");
    const targetReference = fieldValue(operation, "target_ref");
    const subject = { source: "Le personnage", "target.primary": "La cible principale",
      "target.all": "Les cibles", "target.allies": "Les cibles alliées",
      "target.enemies": "Les cibles ennemies", "trigger.source": "L’auteur du déclenchement",
      "trigger.target": "La cible du déclenchement", "area.entities": "Les créatures dans la zone",
      "summon.created": "La créature invoquée" }[targetReference] || "La cible";
    const durationValue = fieldValue(operation, "duration_value");
    const durationUnit = fieldValue(operation, "duration_unit") === "round"
      ? "tour global" : "tour de joueur";
    const duration = durationValue
      ? ` pendant ${durationValue} ${durationUnit}${durationValue === "1" ? "" : "s"}` : "";
    const conditionType = fieldValue(operation, "condition_type");
    const condition = { shield_equipped: " avec un bouclier équipé",
      incoming_attack: " uniquement contre l’attaque déclenchante",
      weapon_equipped: " avec une arme équipée",
      target_poisoned: " si la cible est empoisonnée",
      damage_dealt: " si l’attaque inflige des dégâts" }[conditionType] || "";
    const complete = (text) => `${text}${duration}${condition}.`;

    if (type === "modify_value") {
      const statistic = enabledField(operation, "value_ref");
      const statisticLabel = statistic?.options[statistic.selectedIndex]?.text;
      const mode = fieldValue(operation, "operation_mode");
      const value = fieldValue(operation, "fixed_value");
      if (!statistic?.value || !value) return "Choisis la statistique, la modification et la valeur.";
      const verb = { add: "augmente", subtract: "réduit", set: "fixe",
        minimum: "fixe le minimum de", maximum: "fixe le maximum de",
        override: "remplace", multiply: "multiplie" }[mode] || "modifie";
      const possessedStatistic = statistic.value === "defense.all"
        ? "toutes ses Défenses" : `sa ${statisticLabel}`;
      const renderedValue = mode === "add" ? `+${value}` : value;
      return complete(`${subject} ${verb} ${possessedStatistic} de ${renderedValue}`);
    }
    if (["damage", "modify_attack_damage", "reduce_damage", "reflect_damage",
      "heal", "health_cost", "temporary_health"].includes(type)) {
      const dice = fieldValue(operation, "dice_count");
      const sides = fieldValue(operation, "dice_sides");
      const bonus = fieldValue(operation, "fixed_value");
      const formula = `${dice ? `${dice}d${sides}` : ""}${bonus ? `${dice ? " + " : ""}${bonus}` : ""}`;
      if (!formula) return "Indique une valeur.";
      if (type === "reduce_damage") return complete(`${subject} réduit les dégâts reçus de ${formula}`);
      if (type === "reflect_damage") return complete(`${subject} réduit et renvoie ${formula} dégâts`);
      if (type === "heal") return complete(`${subject} récupère ${formula} PV`);
      if (type === "health_cost") return complete(`${subject} perd ${formula} PV`);
      if (type === "temporary_health") return complete(`${subject} gagne ${formula} PV temporaires`);
      if (type === "modify_attack_damage") return complete(`${subject} ajoute ${formula} dégâts à ses attaques`);
      return complete(`${subject} reçoit ${formula} dégâts`);
    }
    if (type === "move") {
      const distance = fieldValue(operation, "distance_value");
      return distance ? complete(`${subject} se déplace de ${distance} mètres`) : "Indique la distance du déplacement.";
    }
    if (["apply_status", "remove_status", "grant_immunity"].includes(type)) {
      const status = enabledField(operation, "status_ref");
      const label = status?.options[status.selectedIndex]?.text;
      return status?.value ? complete(`${subject} : ${label}`) : "Choisis un état.";
    }
    if (type === "manual_effect") return fieldValue(operation, "description") || "Décris la règle particulière.";
    return "";
  }

  function updateOperationSummary(operation) {
    const type = operation.querySelector("[data-operation-type]");
    operation.querySelector("[data-effect-title]").textContent = type.options[type.selectedIndex].text;
    const previewText = effectPreview(operation);
    const previewLine = operation.querySelector(".operation-preview");
    operation.querySelector("[data-operation-preview]").textContent = previewText;
    previewLine.hidden = !previewText;
    const conditionField = enabledField(operation, "condition_type");
    const advancedSummary = operation.querySelector("[data-advanced-summary]");
    advancedSummary.textContent = conditionField?.value
      ? `· ${conditionField.options[conditionField.selectedIndex].text}` : "";
    updateCapabilityPreview();
  }

  function updateCapabilityPreview() {
    const preview = normalizedEditor.querySelector("[data-capability-description-preview]");
    const incomplete = /^(Indique|Choisis|Décris|Complète)\b/;
    const structureLevel = normalizedEditor.querySelector('[name="structure_level"]').value;
    const sentences = structureLevel === "manual" ? []
      : [...list.querySelectorAll("[data-normalized-operation]")]
      .map((operation) => effectPreview(operation))
      .filter((sentence) => sentence && !incomplete.test(sentence));
    const manualDescription = normalizedEditor.querySelector('[name="manual_description"]').value.trim();
    if (structureLevel !== "structured" && manualDescription) sentences.push(manualDescription);
    preview.replaceChildren(...sentences.map((sentence) => {
      const item = document.createElement("li");
      item.textContent = sentence;
      return item;
    }));
  }

  function toggleOperation(operation) {
    const type = operation.querySelector("[data-operation-type]").value;
    operation.querySelectorAll("[data-fields-for]").forEach((group) => {
      const visible = group.dataset.fieldsFor.split(" ").includes(type);
      group.hidden = !visible;
      group.querySelectorAll("input, select, textarea").forEach((field) => {
        field.disabled = !visible;
      });
    });
    updateOperationSummary(operation);
  }

  function updateGeneralFields() {
    const triggerHidden = normalizedEditor.querySelector('[name="execution_mode"]').value !== "triggered";
    normalizedEditor.querySelector("[data-trigger-field]").hidden = triggerHidden;
    normalizedEditor.querySelector('[name="trigger_event"]').disabled = triggerHidden;
    const rechargeHidden = !normalizedEditor.querySelector('[name="uses_maximum"]').value;
    normalizedEditor.querySelector("[data-recharge-field]").hidden = rechargeHidden;
    normalizedEditor.querySelector('[name="recharge"]').disabled = rechargeHidden;
    const descriptionHidden = normalizedEditor.querySelector('[name="structure_level"]').value === "structured";
    normalizedEditor.querySelector("[data-manual-description]").hidden = descriptionHidden;
    normalizedEditor.querySelector('[name="manual_description"]').disabled = descriptionHidden;
    updateCapabilityPreview();
  }

  function renumber() {
    [...list.querySelectorAll("[data-normalized-operation]")].forEach((operation, index) => {
      operation.querySelector("[data-effect-number]").textContent = index + 1;
      operation.querySelectorAll("[name]").forEach((input) => {
        input.name = input.name.replace(/operation_(?:\d+|__INDEX__)_/, `operation_${index}_`);
      });
      toggleOperation(operation);
    });
    counter.value = list.querySelectorAll("[data-normalized-operation]").length;
  }

  function bind(operation) {
    operation.addEventListener("input", () => updateOperationSummary(operation));
    operation.addEventListener("change", () => updateOperationSummary(operation));
    operation.querySelector("[data-operation-type]").addEventListener("change", () => {
      toggleOperation(operation);
    });
    operation.querySelector("[data-remove-normalized-operation]").addEventListener("click", () => {
      if (list.querySelectorAll("[data-normalized-operation]").length > 1) operation.remove();
      renumber();
    });
  }

  list.querySelectorAll("[data-normalized-operation]").forEach(bind);
  normalizedEditor.querySelector('[name="execution_mode"]').addEventListener("change", updateGeneralFields);
  normalizedEditor.querySelector('[name="structure_level"]').addEventListener("change", updateGeneralFields);
  normalizedEditor.querySelector('[name="uses_maximum"]').addEventListener("input", updateGeneralFields);
  normalizedEditor.querySelector('[name="manual_description"]').addEventListener("input", updateCapabilityPreview);
  normalizedEditor.querySelector("[data-add-normalized-operation]").addEventListener("click", () => {
    const operation = template.content.firstElementChild.cloneNode(true);
    list.append(operation);
    bind(operation);
    renumber();
  });
  renumber();
  updateGeneralFields();
}
