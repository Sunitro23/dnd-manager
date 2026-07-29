# Déploiement Docker

L'image exécute Flask avec Gunicorn sous un utilisateur non privilégié. La
base SQLite et les portraits sont conservés dans le volume Docker
`dnd-manager-data`. Le schéma est initialisé ou migré automatiquement à chaque
démarrage.

## Premier démarrage

Créer le fichier de configuration local :

```bash
cp deploy/docker.env.example .env.docker
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Reporter la clé obtenue dans `SECRET_KEY`, puis construire l'image :

```bash
docker compose build
```

Générer le hash du mot de passe MJ :

```bash
docker compose run --rm --entrypoint flask app --app app hash-password
```

Reporter le hash obtenu dans `GM_PASSWORD_HASH`, puis lancer le service :

```bash
docker compose up -d
docker compose ps
curl http://127.0.0.1:8002/health
```

L'application est accessible sur `http://127.0.0.1:8002`. Pour changer le port
local, définir `APP_PORT` avant `docker compose up`.

## Publication HTTPS

Le port est volontairement lié à `127.0.0.1`. Placer Nginx, Caddy ou Traefik
devant le conteneur, transmettre les en-têtes `Host`, `X-Forwarded-For` et
`X-Forwarded-Proto`, puis définir :

```dotenv
SESSION_COOKIE_SECURE=true
```

Ne pas exposer directement le port Gunicorn sur Internet.

## Mise à jour

```bash
docker compose build --pull
docker compose up -d
docker compose ps
```

Le point d'entrée applique les migrations avant de relancer Gunicorn.

## Sauvegarde

Créer une sauvegarde SQLite cohérente dans le volume :

```bash
docker compose exec app python scripts/backup.py \
  --database /data/dnd_manager.sqlite3 \
  --destination /data/backups \
  --media /data/portraits
```

Copier ensuite les sauvegardes hors du conteneur :

```bash
docker compose cp app:/data/backups ./backups
```

La commande crée une copie cohérente de SQLite et une archive des portraits.

## Journaux et arrêt

```bash
docker compose logs -f app
docker compose down
```

`docker compose down` conserve le volume. Ne pas ajouter `--volumes`, sauf si
la suppression définitive de la base et des portraits est réellement voulue.
