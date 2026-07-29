# Gestionnaire de campagne JDR

Application web légère pour gérer les personnages d'une campagne privée.

## Structure

Le code applicatif est volontairement placé à la racine :

- `app.py` crée l'application Flask ;
- `routes.py`, `characters.py`, `admin.py` et `auth.py` contiennent les écrans ;
- `database.py`, `schema.sql`, `game_data.json` et `rules.py` gèrent les données et calculs ;
- `templates/` et `static/` contiennent l'interface.

Il n'y a ni package Python imbriqué, ni serveur de base de données séparé :
SQLite reste un simple fichier dans `instance/`.

## Prérequis

- Python 3.12 ou version compatible ;
- un environnement virtuel Python.

## Installation locale

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Définir ensuite les variables de configuration :

```bash
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_hex(32))'
.venv/bin/flask --app app hash-password
```

Reporter les deux valeurs générées dans `.env`. La commande `hash-password`
demande le mot de passe MJ et sa confirmation. Le fichier `.env` est chargé
automatiquement et n'est pas versionné.

Initialiser la base et démarrer :

```bash
.venv/bin/flask --app app init-db
.venv/bin/flask --app app run --debug
```

Les classes, races et voies proviennent de `game_data.json` et sont
synchronisées automatiquement.

Chaque niveau accorde un point de voie. Chaque rang coûte un point et les cinq
rangs d'une voie se débloquent dans l'ordre depuis la fiche du personnage.
Les points peuvent être répartis librement entre les deux voies de classe et
les deux voies raciales. Chaque combinaison de bonus de caractéristiques
racial devient sélectionnable sur la fiche lorsque le rang 1 de sa voie est
débloqué. Une seule combinaison peut être active à la fois.
Les bonus passifs permanents non conditionnels sont appliqués automatiquement
aux défenses concernées.

Le site est alors disponible sur `http://127.0.0.1:5000`.

En production derrière HTTPS, définir `SESSION_COOKIE_SECURE=true`.

## Tests

```bash
./scripts/check.sh
```

Ce contrôle exécute Ruff, les 42 tests Python et les vérifications syntaxiques
des fichiers JavaScript.

## Accès

- `/` : campagne et personnages visibles, sans connexion ;
- `/voies` : comparaison publique des voies de classe et des voies raciales ;
- `/personnages/nouveau` : création publique d'un personnage joueur visible ;
- `/personnages/<id>` : consultation d'une fiche visible ;
- `/mj/connexion` : connexion du MJ ;
- `/mj` : vue incluant les personnages secrets, réservée au MJ.

Le MVP n'utilise aucun compte joueur. Les visiteurs pourront modifier les
champs autorisés de tous les personnages visibles.

Les visiteurs pourront également créer des personnages joueurs visibles. Seul
le MJ pourra créer des alliés, PNJ, ennemis ou personnages secrets.

Depuis une fiche visible, un visiteur peut retirer, soigner ou définir les PV,
modifier la description et gérer l'équipement. Les bonus des objets équipés
recalculent les défenses.

Depuis la vue MJ, le bouton « Administrer la fiche » permet de modifier le
niveau, les caractéristiques, l'espèce, le propriétaire, le type et la
visibilité. La classe reste immuable. Les personnages peuvent également être
masqués ou révélés.

Le MJ peut dupliquer une fiche complète, équipement et voies inclus. La
copie est créée sans propriétaire. Le propriétaire et le type d'un personnage
se modifient directement depuis sa fiche administrative.

## Sécurité

- tous les formulaires utilisent une protection CSRF ;
- cinq échecs de connexion MJ bloquent l'adresse IP pendant quinze minutes ;
- les pages envoient une politique CSP et des en-têtes anti-framing ;
- les cookies de session sont `HttpOnly` et `SameSite=Lax` ;
- les formulaires administratifs obsolètes sont refusés en cas de modification
  simultanée.

Après une mise à jour contenant une évolution du schéma, relancer :

```bash
.venv/bin/flask --app app init-db
```

La commande conserve les données existantes et ajoute les tables manquantes.

Les classes, races, voies, rangs et bonus de défense se configurent directement
dans `game_data.json`. Les modifications sont synchronisées au prochain
démarrage de l'application.

## Production

La configuration Gunicorn, Nginx, systemd, HTTPS, sauvegarde quotidienne et
restauration est décrite dans [DEPLOYMENT.md](DEPLOYMENT.md).

Pour un déploiement conteneurisé, utiliser
[DOCKER.md](DOCKER.md). Le projet fournit une image non privilégiée, un
`compose.yaml`, un contrôle de santé et un volume persistant pour SQLite et les
portraits.
