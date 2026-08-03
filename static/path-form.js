const pathDefinitionForm = document.querySelector("[data-path-definition-form]");

if (pathDefinitionForm) {
  const origin = pathDefinitionForm.querySelector('[name="path_type"]:not([type="hidden"])');

  function updateOwner() {
    const selectedOrigin = origin.value;
    pathDefinitionForm.querySelectorAll("[data-owner-for]").forEach((group) => {
      const visible = group.dataset.ownerFor === selectedOrigin;
      group.hidden = !visible;
      group.querySelector("select").disabled = !visible;
    });
  }

  origin.addEventListener("change", updateOwner);
  updateOwner();
}
