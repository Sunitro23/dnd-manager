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

  const ranks = [...pathDefinitionForm.querySelectorAll("[data-path-rank]")];
  ranks.forEach((rank) => rank.addEventListener("toggle", () => {
    if (rank.open) ranks.forEach((other) => { if (other !== rank) other.open = false; });
  }));
  pathDefinitionForm.querySelectorAll("[data-confirm-delete]").forEach((button) => {
    button.addEventListener("click", (event) => {
      if (!window.confirm(button.dataset.confirmDelete)) event.preventDefault();
    });
  });
}
