const sheetMobile = window.matchMedia("(max-width: 760px)");
let activeSheetTab = "character";

function selectInventoryItem(inventory, itemId) {
  inventory.querySelectorAll("[data-inventory-item]")
    .forEach((item) => selectInventoryRow(item, itemId));
  inventory.querySelectorAll("[data-inventory-detail]")
    .forEach((detail) => showInventoryDetail(detail, itemId));
}

function selectInventoryRow(item, itemId) {
  item.classList.toggle("is-selected", item.dataset.inventoryItem === itemId);
}

function showInventoryDetail(detail, itemId) {
  detail.hidden = detail.dataset.inventoryDetail !== itemId;
}

async function loadItemIcons(picker, page = 0) {
  if (picker.dataset.loading === "true") return;
  const moreButton = picker.querySelector("[data-load-more-icons]");
  startIconLoading(picker, moreButton);
  return iconRequest(picker, page, moreButton);
}

function iconRequest(picker, page, moreButton) {
  return fetchIcons(picker, page)
    .then((result) => renderIconResult(picker, moreButton, result))
    .catch(() => showIconError(moreButton))
    .finally(() => { picker.dataset.loading = "false"; });
}

function startIconLoading(picker, button) {
  picker.dataset.loading = "true";
  button.disabled = true;
}

async function fetchIcons(picker, page) {
  const response = await fetchIconPage(picker, page);
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error("Impossible de charger les icônes.");
  return result;
}

function fetchIconPage(picker, page) {
  return fetch(`${picker.dataset.iconUrl}?page=${page}`, {
    headers: {"X-Requested-With": "XMLHttpRequest"},
  });
}

function renderIconResult(picker, button, result) {
  const options = picker.querySelector("[data-icon-options]");
  result.icons.forEach((icon) => options.append(iconButton(icon)));
  picker.dataset.loaded = "true";
  picker.dataset.nextPage = result.next_page ?? "";
  finishIconLoading(button, result.next_page);
}

function finishIconLoading(button, nextPage) {
  button.hidden = nextPage === null;
  button.disabled = false;
}

function iconButton(icon) {
  const button = document.createElement("button");
  Object.assign(button, {type: "button", title: "Utiliser cette icône"});
  button.dataset.iconChoice = icon.path;
  button.append(iconImage(icon.url));
  return button;
}

function iconImage(url) {
  const image = document.createElement("img");
  Object.assign(image, {src: url, alt: ""});
  return image;
}

function showIconError(button) {
  Object.assign(button, {hidden: false, disabled: false, textContent: "Réessayer"});
}

function syncSheetTabs() {
  const tabs = document.querySelectorAll("[data-sheet-tab]");
  const panels = document.querySelectorAll("[data-sheet-panel]");
  if (!tabs.length) return;
  tabs.forEach(syncSheetTab);
  panels.forEach(syncSheetPanel);
}

function syncSheetTab(tab) {
  const active = tab.dataset.sheetTab === activeSheetTab;
  tab.classList.toggle("is-active", active);
  tab.setAttribute("aria-selected", String(active));
}

function syncSheetPanel(panel) {
  const active = panel.dataset.sheetPanel === activeSheetTab;
  panel.hidden = sheetMobile.matches && !active;
  if (sheetMobile.matches && active && panel.tagName === "DETAILS") panel.open = true;
}

function handleSheetClick(event) {
  CLICK_HANDLERS.forEach((handler) => handler(event.target));
  closeOutsideMenus(event.target);
}

function handlePickerToggle(target) {
  const toggle = target.closest("[data-icon-picker-toggle]");
  if (!toggle) return;
  const picker = toggle.nextElementSibling;
  picker.open = !picker.open;
  loadUnloadedPicker(picker);
}

function handlePickerSummary(target) {
  const summary = target.closest("[data-icon-picker] > summary");
  if (summary) loadUnloadedPicker(summary.parentElement);
}

function loadUnloadedPicker(picker) {
  if (picker.open && picker.dataset.loaded !== "true") loadItemIcons(picker);
}

function handleIconChoice(target) {
  const choice = target.closest("[data-icon-choice]");
  if (!choice) return;
  const form = choice.closest(".inventory-detail-form");
  applyIconChoice(form, choice);
  form.requestSubmit();
}

function applyIconChoice(form, choice) {
  form.querySelector('[name="icon_path"]').value = choice.dataset.iconChoice;
  form.querySelector("[data-item-icon-preview]").src = choice.querySelector("img").src;
}

function handleMoreIcons(target) {
  const button = target.closest("[data-load-more-icons]");
  if (!button) return;
  const picker = button.closest("[data-icon-picker]");
  loadItemIcons(picker, Number(picker.dataset.nextPage || 0));
}

function handleSheetTab(target) {
  const tab = target.closest("[data-sheet-tab]");
  if (!tab) return;
  activeSheetTab = tab.dataset.sheetTab;
  syncSheetTabs();
}

function handleInventoryToggle(target) {
  const toggle = target.closest("[data-inventory-toggle]");
  if (!toggle) return;
  const inventory = toggle.closest(".inline-inventory");
  toggleInventoryEditor(inventory, toggle);
}

function toggleInventoryEditor(inventory, toggle) {
  const view = inventory.querySelector("[data-inventory-view]");
  const editor = inventory.querySelector("[data-inventory-editor]");
  const editing = editor.hidden;
  applyEditorState(view, editor, toggle, editing);
}

function applyEditorState(view, editor, toggle, editing) {
  Object.assign(editor, {hidden: !editing});
  Object.assign(view, {hidden: editing});
  toggle.classList.toggle("is-active", editing);
  toggle.textContent = editing ? "Terminer" : "Modifier";
}

function handleCategory(target) {
  const category = target.closest("[data-inventory-category]");
  if (!category) return;
  filterInventory(category.closest(".inventory-browser"), category);
}

function filterInventory(browser, category) {
  const types = category.dataset.inventoryCategory.split(" ");
  activateCategory(browser, category);
  const first = filterInventoryItems(browser, types);
  showFilteredInventory(browser, first);
}

function activateCategory(browser, category) {
  browser.querySelectorAll("[data-inventory-category]").forEach((button) => {
    button.classList.toggle("is-active", button === category);
  });
}

function filterInventoryItems(browser, types) {
  const items = [...browser.querySelectorAll("[data-inventory-item]")];
  items.forEach((item) => filterInventoryItem(item, types));
  return items.find((item) => !item.hidden);
}

function filterInventoryItem(item, types) {
  item.hidden = !(types.includes("all") || types.includes(item.dataset.itemType));
}

function showFilteredInventory(browser, first) {
  if (first) return selectInventoryItem(browser, first.dataset.inventoryItem);
  browser.querySelectorAll("[data-inventory-detail]").forEach((detail) => {
    detail.hidden = true;
  });
}

function handleInventoryItem(target) {
  const item = target.closest("[data-inventory-select]");
  if (!item) return;
  const row = item.closest("[data-inventory-item]");
  const browser = item.closest(".inventory-browser");
  selectOrEquipItem(browser, row, item.dataset.inventorySelect);
}

function selectOrEquipItem(browser, row, itemId) {
  if (row.classList.contains("is-selected")) {
    row.querySelector("[data-equip-form]")?.requestSubmit();
  } else {
    selectInventoryItem(browser, itemId);
  }
}

function handleActionDismiss(target) {
  const dismiss = target.closest("[data-action-dismiss]");
  if (dismiss) dismiss.closest(".action-menu").open = false;
}

function closeOutsideMenus(target) {
  document.querySelectorAll(".action-menu[open]").forEach((menu) => {
    if (!menu.contains(target)) menu.open = false;
  });
}

const CLICK_HANDLERS = [
  handlePickerToggle, handlePickerSummary, handleIconChoice, handleMoreIcons,
  handleSheetTab, handleInventoryToggle, handleCategory, handleInventoryItem,
  handleActionDismiss,
];

document.addEventListener("click", handleSheetClick);

sheetMobile.addEventListener("change", syncSheetTabs);
syncSheetTabs();
