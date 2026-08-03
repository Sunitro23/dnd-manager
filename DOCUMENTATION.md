# Documentation D&D Manager

## Sécurité et configuration

### API et tokens

**⚠️ Important : API_PUBLIC=true par défaut**

Par défaut, l'API est ouverte (`API_PUBLIC=true`) pour faciliter les tests en développement. Cependant, en production, vous devriez :

1. Fermer l'API publique : `API_PUBLIC=false`
2. Utiliser des tokens d'accès : `API_TOKEN=votre_token_securise`

**Piège avec API_TOKEN**

Assurez-vous de ne pas inclure de guillemets dans la valeur du token dans votre fichier `.env` :

```bash
# ❌ INCORRECT - les guillemets font partie de la valeur
API_TOKEN="Amogus"

# ✅ CORRECT - sans guillemets
API_TOKEN=Amogus
```

### Champ owner_id

Le champ `owner_id` dans la table `character` est actuellement **décoratif** et n'implémente pas de contrôle d'accès.

**Comportement actuel :**
- Tout visiteur anonyme peut modifier n'importe quel personnage de la campagne
- Le champ `owner_id` est utilisé à des fins d'information uniquement
- Cohérent avec un groupe de confiance où tous les joueurs sont considérés comme fiables

**Recommandations :**
- Pour une utilisation en groupe de confiance : le champ est décoratif, documentez ce choix
- Pour une utilisation avec contrôle d'accès : implémenter une vérification du `owner_id` dans les endpoints de modification

## Migration de base de données

### Schema version

Le système utilise désormais un numéro de version de schéma pour gérer les migrations :

- Version 1 : Schéma initial
- Version 2 : Extension de la plage des scores de personnage (4-20 au lieu de 8-15)

La version est stockée dans la table `schema_version`.

### Catalogue de jeu

Les classes, races, voies et capacités sont lues directement depuis SQLite.
Une base vide reçoit le catalogue initial de `catalogue_seed.sql` une seule fois.
Les redémarrages suivants ne resynchronisent ni ne remplacent les données éditées.

### Index unique sur les slots d'équipement

Un index unique partiel empêche désormais d'équiper plusieurs items dans le même slot :

```sql
CREATE UNIQUE INDEX equipment_slot_unique 
ON equipment (character_id, slot) WHERE slot != '';
```

## Points de vigilance

### En développement
- `API_PUBLIC=true` est pratique pour les tests
- Utilisez des tokens simples sans guillemets

### En production
- Mettez `API_PUBLIC=false`
- Utilisez des tokens forts et uniques
- Documentez si vous gardez `owner_id` décoratif ou si vous implémentez des contrôles d'accès
- Exécutez le script de vérification des doublons d'équipement avant la première migration

## API de combat étendue

### Nouvelles données exposées

L'endpoint `/api/v1/characters/{character_id}/combat-profile` expose maintenant des données supplémentaires pour la gestion du combat :

#### Résistances, vulnérabilités et immunités
- **resistances** : tableau des résistances/vulnérabilités/immunités permanentes aux types de dégâts
- Chaque entrée contient :
  - `damage_type` : type de dégât (feu, froid, etc.)
  - `level` : "resistance", "vulnerability" ou "immunity"

Ces résistances sont des propriétés permanentes du personnage (provenant de la race, classe, équipement, etc.).

### Nouvelle table de base de données

Une nouvelle table a été ajoutée pour stocker les résistances permanentes :

```sql
-- Table des résistances/vulnérabilités/immunités
CREATE TABLE character_resistance (
    id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL REFERENCES character(id) ON DELETE CASCADE,
    damage_type TEXT NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('resistance', 'vulnerability', 'immunity')),
    source TEXT NOT NULL DEFAULT 'base',
    UNIQUE (character_id, damage_type, source)
);
```

### Données gérées par l'application de combat

Les éléments suivants sont gérés directement par votre application de combat, et non par l'API de profils :

#### Initiative
- Calculée à chaque début de combat : 1d20 + modificateur de Dextérité
- Le modificateur de Dextérité est disponible dans les `abilities` du profil

#### Conditions temporaires
- Statuts comme poison, saignement, paralysé, etc.
- Durée en tours ou minutes
- Disparaissent automatiquement à la fin du combat

### Utilisation pour le combat

L'API fournit :
- Les données permanentes du personnage (stats, défenses, équipement)
- Les résistances/vulnérabilités/immunités permanentes
- Les capacités et ressources disponibles

Votre application de combat gère :
- L'ordre d'initiative (jet de dés à chaque combat)
- Les conditions temporaires et leurs durées
- Le positionnement sur la carte (via Owlbear Rodeo)
- L'état du combat en cours
