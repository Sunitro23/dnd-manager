PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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
    stable_key TEXT UNIQUE,
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
    stable_key TEXT UNIQUE,
    class_id INTEGER NOT NULL REFERENCES character_class(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE,
    abilities TEXT NOT NULL DEFAULT '',
    ranks_json TEXT NOT NULL DEFAULT '[]',
    configured INTEGER NOT NULL DEFAULT 0 CHECK (configured IN (0, 1)),
    UNIQUE (class_id, name)
);

CREATE TABLE IF NOT EXISTS racial_path (
    id INTEGER PRIMARY KEY,
    stable_key TEXT UNIQUE,
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
    physical_bonus INTEGER NOT NULL DEFAULT 0,
    elemental_bonus INTEGER NOT NULL DEFAULT 0,
    spiritual_bonus INTEGER NOT NULL DEFAULT 0,
    configured INTEGER NOT NULL DEFAULT 0 CHECK (configured IN (0, 1)),
    UNIQUE (species_id, name)
);

CREATE TABLE IF NOT EXISTS path_definition (
    id INTEGER PRIMARY KEY,
    stable_key TEXT NOT NULL UNIQUE,
    origin_type TEXT NOT NULL CHECK (origin_type IN ('class', 'racial')),
    origin_id INTEGER NOT NULL,
    legacy_path_id INTEGER NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    abilities TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'published'
        CHECK (status IN ('draft', 'published', 'archived')),
    UNIQUE (origin_type, legacy_path_id)
);

CREATE TABLE IF NOT EXISTS path_rank_definition (
    id INTEGER PRIMARY KEY,
    path_definition_id INTEGER NOT NULL REFERENCES path_definition(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL CHECK (rank > 0),
    name TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('active', 'passive')),
    support TEXT NOT NULL CHECK (support IN ('manual', 'partial', 'full')),
    activation TEXT,
    frequency TEXT,
    effect_manual TEXT NOT NULL DEFAULT '',
    uses_maximum INTEGER,
    recharge TEXT,
    targeting_json TEXT NOT NULL DEFAULT '{"selector":"self"}',
    trigger_json TEXT,
    UNIQUE (path_definition_id, rank, mode)
);

CREATE TABLE IF NOT EXISTS path_operation (
    id INTEGER PRIMARY KEY,
    rank_definition_id INTEGER NOT NULL REFERENCES path_rank_definition(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    operation_type TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT 'selected',
    parameters_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    UNIQUE (rank_definition_id, position)
);

-- Nouveau modèle de règles : un rang peut accorder plusieurs capacités.
CREATE TABLE IF NOT EXISTS path_rank (
    id INTEGER PRIMARY KEY,
    path_definition_id INTEGER NOT NULL REFERENCES path_definition(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL CHECK (rank > 0),
    name TEXT NOT NULL DEFAULT '',
    unlock_level INTEGER,
    UNIQUE (path_definition_id, rank)
);

CREATE TABLE IF NOT EXISTS path_capability (
    id INTEGER PRIMARY KEY,
    path_rank_id INTEGER NOT NULL REFERENCES path_rank(id) ON DELETE CASCADE,
    stable_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    execution_mode TEXT NOT NULL CHECK (
        execution_mode IN ('manual', 'activated', 'triggered', 'permanent')
    ),
    action_cost TEXT NOT NULL DEFAULT 'none' CHECK (
        action_cost IN ('action', 'bonus_action', 'reaction', 'free', 'none')
    ),
    trigger_event TEXT,
    activation_limit TEXT,
    uses_maximum INTEGER CHECK (uses_maximum IS NULL OR uses_maximum > 0),
    recharge TEXT,
    position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
    UNIQUE (path_rank_id, position)
);

CREATE TABLE IF NOT EXISTS capability_target (
    capability_id INTEGER PRIMARY KEY REFERENCES path_capability(id) ON DELETE CASCADE,
    selection_mode TEXT NOT NULL DEFAULT 'none' CHECK (
        selection_mode IN ('none', 'manual', 'automatic', 'area')
    ),
    minimum_targets INTEGER NOT NULL DEFAULT 0 CHECK (minimum_targets >= 0),
    maximum_targets INTEGER CHECK (maximum_targets IS NULL OR maximum_targets > 0),
    range_value REAL,
    range_unit TEXT,
    allegiance TEXT CHECK (allegiance IN ('ally', 'enemy', 'neutral', 'any')),
    entity_type TEXT NOT NULL DEFAULT 'creature',
    allow_self INTEGER NOT NULL DEFAULT 0 CHECK (allow_self IN (0, 1)),
    requires_visibility INTEGER NOT NULL DEFAULT 1 CHECK (requires_visibility IN (0, 1)),
    area_shape TEXT,
    area_size REAL
);

CREATE TABLE IF NOT EXISTS capability_condition (
    id INTEGER PRIMARY KEY,
    capability_id INTEGER NOT NULL REFERENCES path_capability(id) ON DELETE CASCADE,
    condition_scope TEXT NOT NULL CHECK (
        condition_scope IN ('use', 'target', 'execution')
    ),
    condition_type TEXT NOT NULL,
    subject_ref TEXT NOT NULL DEFAULT 'source',
    operator TEXT,
    value_text TEXT,
    value_number REAL,
    position INTEGER NOT NULL DEFAULT 0,
    UNIQUE (capability_id, condition_scope, position)
);

CREATE TABLE IF NOT EXISTS capability_resource (
    id INTEGER PRIMARY KEY,
    capability_id INTEGER NOT NULL REFERENCES path_capability(id) ON DELETE CASCADE,
    resource_ref TEXT NOT NULL,
    cost_type TEXT NOT NULL CHECK (cost_type IN ('fixed', 'dice', 'formula')),
    fixed_value REAL,
    dice_count INTEGER,
    dice_sides INTEGER,
    required INTEGER NOT NULL DEFAULT 1 CHECK (required IN (0, 1)),
    position INTEGER NOT NULL DEFAULT 0,
    UNIQUE (capability_id, position)
);

CREATE TABLE IF NOT EXISTS effect_node (
    id INTEGER PRIMARY KEY,
    capability_id INTEGER NOT NULL REFERENCES path_capability(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES effect_node(id) ON DELETE CASCADE,
    node_type TEXT NOT NULL CHECK (
        node_type IN ('sequence', 'condition', 'choice', 'for_each', 'repeat', 'operation', 'manual_effect')
    ),
    label TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    UNIQUE (capability_id, parent_id, position)
);

CREATE TABLE IF NOT EXISTS effect_operation (
    node_id INTEGER PRIMARY KEY REFERENCES effect_node(id) ON DELETE CASCADE,
    operation_type TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    value_mode TEXT,
    fixed_value REAL,
    dice_count INTEGER,
    dice_sides INTEGER,
    resource_ref TEXT,
    value_ref TEXT,
    damage_type TEXT,
    status_ref TEXT,
    operation_mode TEXT,
    distance_value REAL,
    distance_unit TEXT,
    duration_value INTEGER,
    duration_unit TEXT,
    expiration TEXT,
    frequency TEXT,
    condition_type TEXT,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS status_definition (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    stacking_rule TEXT NOT NULL DEFAULT 'replace',
    default_duration_value INTEGER,
    default_duration_unit TEXT
);

INSERT OR IGNORE INTO status_definition (id,name,description,stacking_rule)
VALUES
    ('fear', 'Peur', 'État de peur défini par les règles de la campagne.', 'refresh'),
    ('poisoned', 'Empoisonné', 'État de poison défini par les règles de la campagne.', 'refresh'),
    ('immobilized', 'Immobilisé', 'La cible ne peut plus se déplacer.', 'replace'),
    ('stable', 'Stable', 'La cible est stabilisée.', 'replace');

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
    strength INTEGER NOT NULL DEFAULT 8 CHECK (strength BETWEEN 4 AND 20),
    dexterity INTEGER NOT NULL DEFAULT 8 CHECK (dexterity BETWEEN 4 AND 20),
    constitution INTEGER NOT NULL DEFAULT 8 CHECK (constitution BETWEEN 4 AND 20),
    intelligence INTEGER NOT NULL DEFAULT 8 CHECK (intelligence BETWEEN 4 AND 20),
    wisdom INTEGER NOT NULL DEFAULT 8 CHECK (wisdom BETWEEN 4 AND 20),
    charisma INTEGER NOT NULL DEFAULT 8 CHECK (charisma BETWEEN 4 AND 20),
    current_hp INTEGER NOT NULL DEFAULT 1,
    max_hp INTEGER NOT NULL DEFAULT 1 CHECK (max_hp > 0),
    estus_available INTEGER NOT NULL DEFAULT 1 CHECK (estus_available IN (0, 1)),
    mortal_damage INTEGER NOT NULL DEFAULT 0 CHECK (mortal_damage BETWEEN 0 AND 3),
    souls INTEGER NOT NULL DEFAULT 0 CHECK (souls >= 0),
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
    path_type TEXT NOT NULL CHECK (path_type IN ('class', 'racial', 'custom')),
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

CREATE TABLE IF NOT EXISTS character_custom_rank (
    character_id INTEGER NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 5),
    description TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (character_id, rank)
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

CREATE UNIQUE INDEX IF NOT EXISTS equipment_slot_unique
ON equipment (character_id, slot) WHERE slot != '';

CREATE TABLE IF NOT EXISTS login_attempt (
    id INTEGER PRIMARY KEY,
    ip_address TEXT NOT NULL,
    attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS login_attempt_ip_date
ON login_attempt (ip_address, attempted_at);

CREATE TABLE IF NOT EXISTS character_resistance (
    id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    damage_type TEXT NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('resistance', 'vulnerability', 'immunity')),
    source TEXT NOT NULL DEFAULT 'base',
    UNIQUE (character_id, damage_type, source)
);

CREATE INDEX IF NOT EXISTS character_resistance_lookup
ON character_resistance (character_id, damage_type);

INSERT OR IGNORE INTO campaign (id, name) VALUES (1, 'Notre campagne');
