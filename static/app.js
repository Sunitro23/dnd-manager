document.addEventListener("submit", (event) => {
  const message = event.target.dataset.confirm;
  if (message && !window.confirm(message)) {
    event.preventDefault();
  }
});

const currentUrl = new URL(window.location.href);
if (currentUrl.searchParams.get("created") === "1") {
  localStorage.removeItem("dnd-manager-character-draft");
  currentUrl.searchParams.delete("created");
  window.history.replaceState({}, "", currentUrl);
}

const sheetMobile = window.matchMedia("(max-width: 760px)");
let activeSheetTab = "character";

function selectInventoryItem(inventory, itemId) {
  inventory.querySelectorAll("[data-inventory-item]").forEach((item) => {
    item.classList.toggle("is-selected", item.dataset.inventoryItem === itemId);
  });
  inventory.querySelectorAll("[data-inventory-detail]").forEach((detail) => {
    detail.hidden = detail.dataset.inventoryDetail !== itemId;
  });
}

async function loadItemIcons(picker, page = 0) {
  if (picker.dataset.loading === "true") {
    return;
  }
  picker.dataset.loading = "true";
  const moreButton = picker.querySelector("[data-load-more-icons]");
  moreButton.disabled = true;
  try {
    const response = await fetch(`${picker.dataset.iconUrl}?page=${page}`, {
      headers: {"X-Requested-With": "XMLHttpRequest"},
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error("Impossible de charger les icônes.");
    }
    const options = picker.querySelector("[data-icon-options]");
    result.icons.forEach((icon) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.iconChoice = icon.path;
      button.title = "Utiliser cette icône";
      const image = document.createElement("img");
      image.src = icon.url;
      image.alt = "";
      button.append(image);
      options.append(button);
    });
    picker.dataset.loaded = "true";
    picker.dataset.nextPage = result.next_page ?? "";
    moreButton.hidden = result.next_page === null;
    moreButton.disabled = false;
  } catch {
    moreButton.hidden = false;
    moreButton.disabled = false;
    moreButton.textContent = "Réessayer";
  } finally {
    picker.dataset.loading = "false";
  }
}

function syncSheetTabs() {
  const tabs = document.querySelectorAll("[data-sheet-tab]");
  const panels = document.querySelectorAll("[data-sheet-panel]");
  if (!tabs.length) {
    return;
  }
  tabs.forEach((tab) => {
    const active = tab.dataset.sheetTab === activeSheetTab;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  panels.forEach((panel) => {
    const active = panel.dataset.sheetPanel === activeSheetTab;
    panel.hidden = sheetMobile.matches && !active;
    if (sheetMobile.matches && active && panel.tagName === "DETAILS") {
      panel.open = true;
    }
  });
}

document.addEventListener("click", (event) => {
  const pickerToggle = event.target.closest("[data-icon-picker-toggle]");
  if (pickerToggle) {
    const picker = pickerToggle.nextElementSibling;
    picker.open = !picker.open;
    if (picker.open && picker.dataset.loaded !== "true") {
      loadItemIcons(picker);
    }
  }

  const pickerSummary = event.target.closest("[data-icon-picker] > summary");
  if (pickerSummary) {
    const picker = pickerSummary.parentElement;
    if (picker.dataset.loaded !== "true") {
      loadItemIcons(picker);
    }
  }

  const iconChoice = event.target.closest("[data-icon-choice]");
  if (iconChoice) {
    const form = iconChoice.closest(".inventory-detail-form");
    form.querySelector('[name="icon_path"]').value = iconChoice.dataset.iconChoice;
    form.querySelector("[data-item-icon-preview]").src =
      iconChoice.querySelector("img").src;
    form.requestSubmit();
  }

  const moreIcons = event.target.closest("[data-load-more-icons]");
  if (moreIcons) {
    const picker = moreIcons.closest("[data-icon-picker]");
    loadItemIcons(picker, Number(picker.dataset.nextPage || 0));
  }

  const tab = event.target.closest("[data-sheet-tab]");
  if (tab) {
    activeSheetTab = tab.dataset.sheetTab;
    syncSheetTabs();
  }

  const inventoryToggle = event.target.closest("[data-inventory-toggle]");
  if (inventoryToggle) {
    const inventory = inventoryToggle.closest(".inline-inventory");
    const view = inventory.querySelector("[data-inventory-view]");
    const editor = inventory.querySelector("[data-inventory-editor]");
    const editing = editor.hidden;
    editor.hidden = !editing;
    view.hidden = editing;
    inventoryToggle.classList.toggle("is-active", editing);
    inventoryToggle.textContent = editing ? "Terminer" : "Modifier";
  }

  const category = event.target.closest("[data-inventory-category]");
  if (category) {
    const browser = category.closest(".inventory-browser");
    const acceptedTypes = category.dataset.inventoryCategory.split(" ");
    browser.querySelectorAll("[data-inventory-category]").forEach((button) => {
      button.classList.toggle("is-active", button === category);
    });
    let firstVisible;
    browser.querySelectorAll("[data-inventory-item]").forEach((item) => {
      const visible =
        acceptedTypes.includes("all") || acceptedTypes.includes(item.dataset.itemType);
      item.hidden = !visible;
      if (visible && !firstVisible) {
        firstVisible = item;
      }
    });
    if (firstVisible) {
      selectInventoryItem(browser, firstVisible.dataset.inventoryItem);
    } else {
      browser.querySelectorAll("[data-inventory-detail]").forEach((detail) => {
        detail.hidden = true;
      });
    }
  }

  const inventoryItem = event.target.closest("[data-inventory-select]");
  if (inventoryItem) {
    const row = inventoryItem.closest("[data-inventory-item]");
    const browser = inventoryItem.closest(".inventory-browser");
    if (row.classList.contains("is-selected")) {
      row.querySelector("[data-equip-form]")?.requestSubmit();
    } else {
      selectInventoryItem(browser, inventoryItem.dataset.inventorySelect);
    }
  }

  const actionDismiss = event.target.closest("[data-action-dismiss]");
  if (actionDismiss) {
    actionDismiss.closest(".action-menu").open = false;
  }

  document.querySelectorAll(".action-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) {
      menu.open = false;
    }
  });
});

sheetMobile.addEventListener("change", syncSheetTabs);
syncSheetTabs();

function syncItemFields(form) {
  const type = form.querySelector('[name="item_type"]')?.value;
  form.querySelectorAll("[data-fields-for]").forEach((group) => {
    group.hidden = !group.dataset.fieldsFor.split(" ").includes(type);
  });
}

document.querySelectorAll("[data-item-fields]").forEach((fields) => {
  syncItemFields(fields.closest("form"));
});

document.addEventListener("change", (event) => {
  if (event.target.matches('[name="item_type"]')) {
    syncItemFields(event.target.form);
  }
  const field = event.target.closest("[data-submit-on-change]");
  if (field) {
    if (field.checkValidity()) {
      field.form.requestSubmit();
    }
  }
});

document.addEventListener("submit", async (event) => {
  if (event.defaultPrevented) {
    return;
  }
  const form = event.target.closest("[data-async-form]");
  if (form) {
    event.preventDefault();
    const status = document.querySelector(".save-status");
    const formData = new FormData(form);
    if (event.submitter?.name && !formData.has(event.submitter.name)) {
      formData.append(event.submitter.name, event.submitter.value);
    }
    const controls = form.querySelectorAll("input, select, textarea, button");
    controls.forEach((control) => {
      control.disabled = true;
    });

    if (status) {
      status.hidden = false;
      status.className = "save-status";
      status.textContent = "Enregistrement…";
    }

    try {
      const formUrl = new URL(form.getAttribute("action"), window.location.href);
      const response = await fetch(formUrl, {
        method: "POST",
        body: formData,
        headers: {"X-Requested-With": "XMLHttpRequest"},
      });
      const responseText = await response.text();
      let result;
      try {
        result = JSON.parse(responseText);
      } catch {
        const errorPage = new DOMParser().parseFromString(
          responseText,
          "text/html",
        );
        const serverMessage =
          errorPage.querySelector(".error-page p")?.textContent ||
          errorPage.querySelector("title")?.textContent;
        throw new Error(
          serverMessage || `Erreur serveur (${response.status}).`,
        );
      }
      if (!response.ok || !result.ok) {
        throw new Error(result.message || "L’enregistrement a échoué.");
      }

      if (result.current_hp !== undefined) {
        const hp = document.getElementById("current-hp");
        if (hp.matches("input")) {
          hp.value = result.current_hp;
          hp.max = result.max_hp;
        } else {
          hp.textContent = result.current_hp;
        }
        document.querySelector(".hp-maximum").textContent =
          `Max ${result.max_hp}`;
      }

      if (result.estus_available !== undefined) {
        const estusForm = document.querySelector(
          '.hp-popup input[name="action"][value="estus"]',
        )?.form;
        const button = estusForm?.querySelector("button");
        if (button) {
          button.disabled = !result.estus_available;
          button.querySelector("small").textContent =
            result.estus_available ? "Soin complet" : "Déjà utilisé";
        }
      }

      if (result.action_key) {
        const action = document.querySelector(
          `[data-action-key="${CSS.escape(result.action_key)}"]`,
        );
        const uses = action?.querySelector("[data-action-uses]");
        const button = action?.querySelector(".use-action");
        if (uses) {
          const total = uses.textContent.match(/\/(\d+)/)?.[1];
          uses.textContent = total
            ? `${result.remaining}/${total} restantes`
            : `${result.remaining} restante${result.remaining === 1 ? "" : "s"}`;
        }
        if (button) {
          button.disabled = result.remaining === 0;
        }
      }

      if (result.image_url) {
        const portrait = document.createElement("img");
        portrait.src = `${result.image_url}?v=${Date.now()}`;
        portrait.alt =
          `Portrait de ${document.querySelector(".character-header h1").textContent}`;
        document.querySelector(".portrait-control").replaceChildren(portrait);
      }

      if (result.refresh_sheet) {
        const page = await fetch(window.location.href);
        const documentCopy = new DOMParser().parseFromString(
          await page.text(),
          "text/html",
        );
        for (const selector of [
          ".character-header",
          ".sheet-overview",
          ".progression-panel",
          ".inline-inventory",
          ".equipment-panel",
        ]) {
          const current = document.querySelector(selector);
          const updated = documentCopy.querySelector(selector);
          if (current && updated) {
            current.replaceWith(updated);
          }
        }
        syncSheetTabs();
        document.querySelectorAll("[data-item-fields]").forEach((fields) => {
          syncItemFields(fields.closest("form"));
        });
        if (result.selected_item_id !== undefined) {
          const browser = document.querySelector(".inventory-browser");
          if (browser) {
            selectInventoryItem(browser, String(result.selected_item_id));
          }
        }
      }

      if (status) {
        status.classList.add("is-saved");
        status.textContent = result.message || "Enregistré.";
        window.setTimeout(() => {
          status.hidden = true;
        }, 2000);
      }
    } catch (error) {
      if (status) {
        status.classList.add("is-error");
        status.textContent = error.message;
      }
    } finally {
      controls.forEach((control) => {
        control.disabled = false;
      });
    }
  }
});
