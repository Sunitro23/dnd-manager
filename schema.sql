PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS campaign (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS player (
    id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS character_class (
    id INTEGER PRIMARY KEY,
    stable_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    hit_die INTEGER NOT NULL CHECK (hit_die IN (6, 8, 10, 12)),
    strength_bonus INTEGER NOT NULL DEFAULT 0 CHECK (strength_bonus BETWEEN 0 AND 3),
    dexterity_bonus INTEGER NOT NULL DEFAULT 0 CHECK (dexterity_bonus BETWEEN 0 AND 3),
    constitution_bonus INTEGER NOT NULL DEFAULT 0 CHECK (constitution_bonus BETWEEN 0 AND 3),
    intelligence_bonus INTEGER NOT NULL DEFAULT 0 CHECK (intelligence_bonus BETWEEN 0 AND 3),
    wisdom_bonus INTEGER NOT NULL DEFAULT 0 CHECK (wisdom_bonus BETWEEN 0 AND 3),
    charisma_bonus INTEGER NOT NULL DEFAULT 0 CHECK (charisma_bonus BETWEEN 0 AND 3),
    configured INTEGER NOT NULL DEFAULT 0 CHECK (configured IN (0, 1))
);

CREATE TABLE IF NOT EXISTS species (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    traits TEXT NOT NULL DEFAULT '',
    size TEXT,
    speed INTEGER,
    physical_bonus INTEGER NOT NULL DEFAULT 0,
    elemental_bonus INTEGER NOT NULL DEFAULT 0,
    spiritual_bonus INTEGER NOT NULL DEFAULT 0,
    configured INTEGER NOT NULL DEFAULT 0 CHECK (configured IN (0, 1))
);

CREATE TABLE IF NOT EXISTS class_path (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL REFERENCES character_class(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE,
    abilities TEXT NOT NULL DEFAULT '',
    ranks_json TEXT NOT NULL DEFAULT '[]',
    configured INTEGER NOT NULL DEFAULT 0 CHECK (configured IN (0, 1)),
    UNIQUE (class_id, name)
);

CREATE TABLE IF NOT EXISTS racial_path (
    id INTEGER PRIMARY KEY,
    species_id INTEGER NOT NULL REFERENCES species(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE,
    abilities TEXT NOT NULL DEFAULT '',
    ranks_json TEXT NOT NULL DEFAULT '[]',
    strength_bonus INTEGER NOT NULL DEFAULT 0,
    dexterity_bonus INTEGER NOT NULL DEFAULT 0,
    constitution_bonus INTEGER NOT NULL DEFAULT 0,
    intelligence_bonus INTEGER NOT NULL DEFAULT 0,
    wisdom_bonus INTEGER NOT NULL DEFAULT 0,
    charisma_bonus INTEGER NOT NULL DEFAULT 0,
    configured INTEGER NOT NULL DEFAULT 0 CHECK (configured IN (0, 1)),
    UNIQUE (species_id, name)
);

CREATE TABLE IF NOT EXISTS character (
    id INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL DEFAULT 1 REFERENCES campaign(id),
    owner_id INTEGER REFERENCES player(id) ON DELETE SET NULL,
    class_id INTEGER REFERENCES character_class(id),
    species_id INTEGER REFERENCES species(id),
    class_path_id INTEGER REFERENCES class_path(id),
    racial_path_id INTEGER REFERENCES racial_path(id),
    name TEXT NOT NULL,
    character_type TEXT NOT NULL CHECK (
        character_type IN ('player', 'ally', 'npc', 'enemy')
    ),
    visibility TEXT NOT NULL DEFAULT 'campaign' CHECK (
        visibility IN ('campaign', 'gm')
    ),
    level INTEGER NOT NULL DEFAULT 1 CHECK (level BETWEEN 1 AND 20),
    description TEXT NOT NULL DEFAULT '',
    personal_info TEXT NOT NULL DEFAULT '',
    portrait_filename TEXT,
    strength INTEGER NOT NULL DEFAULT 8 CHECK (strength BETWEEN 8 AND 15),
    dexterity INTEGER NOT NULL DEFAULT 8 CHECK (dexterity BETWEEN 8 AND 15),
    constitution INTEGER NOT NULL DEFAULT 8 CHECK (constitution BETWEEN 8 AND 15),
    intelligence INTEGER NOT NULL DEFAULT 8 CHECK (intelligence BETWEEN 8 AND 15),
    wisdom INTEGER NOT NULL DEFAULT 8 CHECK (wisdom BETWEEN 8 AND 15),
    charisma INTEGER NOT NULL DEFAULT 8 CHECK (charisma BETWEEN 8 AND 15),
    current_hp INTEGER NOT NULL DEFAULT 1,
    max_hp INTEGER NOT NULL DEFAULT 1 CHECK (max_hp > 0),
    estus_available INTEGER NOT NULL DEFAULT 1 CHECK (estus_available IN (0, 1)),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS character_public_list
ON character (visibility, character_type, name);

CREATE INDEX IF NOT EXISTS character_owner
ON character (owner_id);

CREATE TABLE IF NOT EXISTS character_rank (
    id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    path_type TEXT NOT NULL CHECK (path_type IN ('class', 'racial')),
    path_id INTEGER NOT NULL,
    rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 5),
    unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (character_id, path_type, path_id, rank)
);

CREATE TABLE IF NOT EXISTS character_action_use (
    character_id INTEGER NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    path_type TEXT NOT NULL CHECK (path_type IN ('class', 'racial')),
    path_id INTEGER NOT NULL,
    rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 5),
    uses_spent INTEGER NOT NULL DEFAULT 0 CHECK (uses_spent >= 0),
    PRIMARY KEY (character_id, path_type, path_id, rank)
);

CREATE TABLE IF NOT EXISTS equipment (
    id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    item_type TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    equipped INTEGER NOT NULL DEFAULT 0 CHECK (equipped IN (0, 1)),
    slot TEXT NOT NULL DEFAULT '',
    icon_path TEXT NOT NULL DEFAULT '',
    physical_bonus INTEGER NOT NULL DEFAULT 0,
    elemental_bonus INTEGER NOT NULL DEFAULT 0,
    spiritual_bonus INTEGER NOT NULL DEFAULT 0,
    damage_dice TEXT NOT NULL DEFAULT '',
    damage_type TEXT NOT NULL DEFAULT '',
    uses TEXT NOT NULL DEFAULT '',
    stat TEXT NOT NULL DEFAULT '',
    stat_bonus INTEGER NOT NULL DEFAULT 0,
    effect TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS equipment_character
ON equipment (character_id, equipped, name);

CREATE TABLE IF NOT EXISTS login_attempt (
    id INTEGER PRIMARY KEY,
    ip_address TEXT NOT NULL,
    attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS login_attempt_ip_date
ON login_attempt (ip_address, attempted_at);

INSERT OR IGNORE INTO campaign (id, name) VALUES (1, 'Notre campagne');
