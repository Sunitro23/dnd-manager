import sqlite3
from dataclasses import asdict

from dnd_manager.characters.inventory.contracts import (
    DuplicateResult,
    EquipmentView,
    ItemCopy,
    ItemState,
    QuickCreateResult,
    SaveItemResult,
    ToggleState,
)
from dnd_manager.characters.inventory.item_form import normalize_slot, recalculate_hp
from dnd_manager.shared.errors import ConcurrentUpdate, InvalidRequest, RepositoryUnavailable

ITEM_FIELDS = (
    "name", "item_type", "quantity", "equipped", "physical_bonus",
    "elemental_bonus", "spiritual_bonus", "damage_dice", "damage_type",
    "uses", "stat", "stat_bonus", "icon_path", "effect", "notes",
)


class SqliteInventoryRepository:
    def __init__(self, database):
        self.database = database

    def find_item(self, character_id, public_only, command):
        values = (command.equipment_id, character_id)
        row = self.database.execute(find_item_query(public_only), values).fetchone()
        return item_state(row)

    def save_consumption(self, state, result):
        try:
            persist_consumption(self.database, state, result)
        except sqlite3.Error as error:
            self.fail(error)

    def find_toggle(self, character_id, public_only, command):
        row = find_toggle_row(self.database, character_id, public_only, command)
        return toggle_state(self.database, row)

    def save_toggle(self, state, result):
        try:
            persist_toggle(self.database, state, result)
        except sqlite3.Error as error:
            self.fail(error)

    def character_exists(self, character_id, public_only):
        try:
            return find_character(self.database, character_id, public_only)
        except sqlite3.Error as error:
            self.fail(error)

    def create_quick_item(self, character_id, name, command):
        try:
            return insert_quick_item(self.database, character_id, name, command)
        except sqlite3.Error as error:
            self.fail(error)

    def find_delete(self, character_id, public_only, command):
        row = find_toggle_row(self.database, character_id, public_only, command)
        return toggle_state(self.database, row)

    def save_delete(self, state, result):
        try:
            persist_delete(self.database, state, result)
        except sqlite3.Error as error:
            self.fail(error)

    def find_copy(self, character_id, public_only, command):
        try:
            row = find_copy_row(self.database, character_id, public_only, command)
            return item_copy(row)
        except sqlite3.Error as error:
            self.fail(error)

    def save_copy(self, item):
        try:
            return insert_copy(self.database, item)
        except sqlite3.Error as error:
            self.fail(error)

    def save_item(self, character_id, command):
        try:
            equipment_id = persist_item(self.database, character_id, command)
            return SaveItemResult(character_id, equipment_id)
        except ValueError as error:
            self.database.rollback()
            raise InvalidRequest(str(error)) from error
        except sqlite3.Error as error:
            self.fail(error)

    def fail(self, error):
        self.database.rollback()
        raise RepositoryUnavailable("L’inventaire est momentanément indisponible.") from error


def find_item_query(public_only):
    visibility = "AND c.visibility = 'campaign'" if public_only else ""
    return ("SELECT e.id, e.character_id, e.name, e.item_type, e.quantity "
            "FROM equipment e JOIN character c ON c.id = e.character_id "
            f"WHERE e.id = ? AND e.character_id = ? {visibility}")


def item_state(row):
    if row is None:
        return None
    return ItemState(row["character_id"], row["id"], row["name"],
                     row["item_type"], row["quantity"])


def persist_consumption(database, state, result):
    cursor = consumption_operation(database, state, result)
    commit_consumption(database, cursor)


def consumption_operation(database, state, result):
    if result.remaining == 0:
        query = "DELETE FROM equipment WHERE id = ? AND character_id = ? AND quantity = ?"
        return database.execute(query, (state.equipment_id, state.character_id, state.quantity))
    query = ("UPDATE equipment SET quantity = quantity - 1 "
             "WHERE id = ? AND character_id = ? AND quantity = ?")
    return database.execute(query, (state.equipment_id, state.character_id, state.quantity))


def commit_consumption(database, cursor):
    if cursor.rowcount == 0:
        database.rollback()
        raise ConcurrentUpdate("La quantité de cet objet a déjà changé.")
    database.commit()


def find_toggle_row(database, character_id, public_only, command):
    visibility = "AND c.visibility = 'campaign'" if public_only else ""
    query = ("SELECT e.*, c.level, c.constitution, c.current_hp, c.max_hp, c.version, "
             "cc.hit_die, cc.constitution_bonus AS class_bonus, "
             "COALESCE(rp.constitution_bonus, 0) AS racial_bonus, "
             "COALESCE((SELECT SUM(a.stat_bonus) FROM equipment a WHERE a.character_id = c.id "
             "AND a.equipped = 1 AND a.item_type = 'accessory' AND a.stat = 'CON'), 0) accessory_bonus "
             "FROM equipment e JOIN character c ON c.id = e.character_id "
             "JOIN character_class cc ON cc.id = c.class_id "
             "LEFT JOIN racial_path rp ON rp.id = c.racial_path_id "
             f"WHERE e.id = ? AND e.character_id = ? {visibility}")
    return database.execute(query, (command.equipment_id, character_id)).fetchone()


def toggle_state(database, row):
    if row is None:
        return None
    bonus = row["class_bonus"] + row["racial_bonus"] + row["accessory_bonus"]
    occupied = occupied_slots(database, row["character_id"], row["id"])
    return ToggleState(row["character_id"], row["id"], row["item_type"],
                       bool(row["equipped"]), row["slot"], occupied, row["level"],
                       row["constitution"], bonus, row["stat"], row["stat_bonus"],
                       row["hit_die"], row["current_hp"], row["max_hp"], row["version"])


def occupied_slots(database, character_id, equipment_id):
    query = ("SELECT slot FROM equipment WHERE character_id = ? AND equipped = 1 "
             "AND slot != '' AND id != ?")
    rows = database.execute(query, (character_id, equipment_id)).fetchall()
    return tuple(row["slot"] for row in rows)


def persist_toggle(database, state, result):
    cursor = update_equipment_state(database, state, result)
    require_updated(database, cursor, "L’état de cet objet a déjà changé.")
    cursor = update_character_health(database, state, result)
    require_updated(database, cursor, "La fiche a été modifiée simultanément.")
    database.commit()


def update_equipment_state(database, state, result):
    query = ("UPDATE equipment SET equipped = ?, slot = ? "
             "WHERE id = ? AND character_id = ? AND equipped = ? AND slot = ?")
    values = (result.equipped, result.slot, state.equipment_id, state.character_id,
              state.equipped, state.slot)
    return database.execute(query, values)


def update_character_health(database, state, result):
    query = ("UPDATE character SET current_hp = ?, max_hp = ?, version = version + 1, "
             "updated_at = CURRENT_TIMESTAMP WHERE id = ? AND version = ?")
    values = (result.current_hp, result.maximum_hp, state.character_id, state.version)
    return database.execute(query, values)


def require_updated(database, cursor, message):
    if cursor.rowcount == 0:
        database.rollback()
        raise ConcurrentUpdate(message)


def insert_quick_item(database, character_id, name, command):
    query = "INSERT INTO equipment (character_id, name, item_type) VALUES (?, ?, ?)"
    cursor = database.execute(query, (character_id, name, command.item_type))
    database.commit()
    return QuickCreateResult(character_id, cursor.lastrowid, name, command.item_type)


def find_character(database, character_id, public_only):
    visibility = "AND visibility = 'campaign'" if public_only else ""
    query = f"SELECT 1 FROM character WHERE id = ? {visibility}"
    return database.execute(query, (character_id,)).fetchone() is not None


def persist_delete(database, state, result):
    cursor = delete_equipment_row(database, state)
    require_updated(database, cursor, "Cet objet a déjà été modifié.")
    cursor = update_character_health(database, state, result)
    require_updated(database, cursor, "La fiche a été modifiée simultanément.")
    database.commit()


def delete_equipment_row(database, state):
    query = ("DELETE FROM equipment WHERE id = ? AND character_id = ? "
             "AND equipped = ? AND slot = ?")
    values = (state.equipment_id, state.character_id, state.equipped, state.slot)
    return database.execute(query, values)


def find_copy_row(database, character_id, public_only, command):
    visibility = "AND c.visibility = 'campaign'" if public_only else ""
    query = ("SELECT e.* FROM equipment e JOIN character c ON c.id = e.character_id "
             f"WHERE e.id = ? AND e.character_id = ? {visibility}")
    return database.execute(query, (command.equipment_id, character_id)).fetchone()


def item_copy(row):
    if row is None:
        return None
    names = ("character_id", "name", "item_type", "quantity", "physical_bonus",
             "elemental_bonus", "spiritual_bonus", "damage_dice", "damage_type",
             "uses", "stat", "stat_bonus", "icon_path", "effect", "notes")
    return ItemCopy(*(row[name] for name in names))


def insert_copy(database, item):
    query = ("INSERT INTO equipment (character_id, name, item_type, quantity, equipped, "
             "physical_bonus, elemental_bonus, spiritual_bonus, damage_dice, damage_type, "
             "uses, stat, stat_bonus, icon_path, effect, notes) "
             "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
    cursor = database.execute(query, copy_values(item))
    database.commit()
    return DuplicateResult(item.character_id, cursor.lastrowid, item.name)


def copy_values(item):
    return (item.character_id, item.name, item.item_type, item.quantity,
            item.physical_bonus, item.elemental_bonus, item.spiritual_bonus,
            item.damage_dice, item.damage_type, item.uses, item.stat,
            item.stat_bonus, item.icon_path, item.effect, item.notes)


def persist_item(database, character_id, command):
    if command.equipment_id is None:
        return create_equipment(database, character_id, command.data)
    update_equipment(database, character_id, command.equipment_id, command.data)
    return command.equipment_id


def equipment_for_character(database, character_id):
    query = ("SELECT * FROM equipment WHERE character_id = ? "
             "ORDER BY equipped DESC, name COLLATE NOCASE")
    rows = database.execute(query, (character_id,)).fetchall()
    return tuple(equipment_view(row) for row in rows)


def find_equipment(database, character_id, equipment_id):
    query = "SELECT * FROM equipment WHERE id = ? AND character_id = ?"
    return equipment_view(database.execute(query, (equipment_id, character_id)).fetchone())


def equipment_view(row):
    if row is None:
        return None
    names = ("id", "character_id", "name", "item_type", "quantity", "equipped",
             "physical_bonus", "elemental_bonus", "spiritual_bonus", "damage_dice",
             "damage_type", "uses", "stat", "stat_bonus", "slot", "icon_path",
             "effect", "notes")
    return EquipmentView(*(row[name] for name in names))


def create_equipment(database, character_id, data):
    values = {**asdict(data), "character_id": character_id}
    equipment_id = database.execute(insert_item_sql(), values).lastrowid
    return finish_item_save(database, character_id, equipment_id, values)


def insert_item_sql():
    fields = ", ".join(ITEM_FIELDS)
    placeholders = ", ".join(f":{field}" for field in ITEM_FIELDS)
    return f"INSERT INTO equipment (character_id, {fields}) VALUES (:character_id, {placeholders})"


def update_equipment(database, character_id, equipment_id, data):
    values = {**asdict(data), "id": equipment_id, "character_id": character_id}
    assignments = ", ".join(f"{field} = :{field}" for field in ITEM_FIELDS)
    query = f"UPDATE equipment SET {assignments} WHERE id = :id AND character_id = :character_id"
    database.execute(query, values)
    finish_item_save(database, character_id, equipment_id, values)


def finish_item_save(database, character_id, equipment_id, values):
    require_slot(database, character_id, equipment_id, values)
    recalculate_hp(database, character_id)
    database.commit()
    return equipment_id


def require_slot(database, character_id, equipment_id, values):
    slot = normalize_slot(database, character_id, equipment_id,
                          values["item_type"], bool(values["equipped"]))
    if values["equipped"] and slot is None:
        raise ValueError("Aucun emplacement compatible n’est disponible.")
