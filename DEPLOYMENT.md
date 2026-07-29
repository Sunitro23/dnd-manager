# Déploiement sur dnd.sunitro.de

Cette procédure vise un petit serveur Debian ou Ubuntu avec Nginx, systemd et
un certificat Let's Encrypt. Elle conserve l'application et ses données dans
des emplacements séparés :

- code : `/opt/dnd-manager` ;
- base et fichiers : `/var/lib/dnd-manager` ;
- sauvegardes : `/var/backups/dnd-manager` ;
- secrets : `/etc/dnd-manager.env`.

## 1. Préparer le serveur

Créer l'utilisateur de service et les répertoires :

```bash
sudo useradd --system --home /var/lib/dnd-manager --shell /usr/sbin/nologin dnd-manager
sudo mkdir -p /opt/dnd-manager /var/lib/dnd-manager/media /var/backups/dnd-manager
sudo chown -R dnd-manager:dnd-manager /var/lib/dnd-manager /var/backups/dnd-manager
```

Copier le projet dans `/opt/dnd-manager`, puis installer l'environnement :

```bash
cd /opt/dnd-manager
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo chown -R root:root /opt/dnd-manager
```

## 2. Configurer les secrets

Générer la clé de session :

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Générer le hash du mot de passe MJ depuis le projet :

```bash
/opt/dnd-manager/.venv/bin/flask --app /opt/dnd-manager/app.py hash-password
```

Copier `deploy/production.env.example` vers `/etc/dnd-manager.env`, remplacer
les deux valeurs, puis protéger le fichier :

```bash
sudo chown root:dnd-manager /etc/dnd-manager.env
sudo chmod 640 /etc/dnd-manager.env
```

Initialiser ou mettre à jour le schéma :

```bash
sudo -u dnd-manager env \
  SECRET_KEY=initialisation \
  GM_PASSWORD_HASH=initialisation \
  DATABASE_PATH=/var/lib/dnd-manager/dnd-manager.sqlite3 \
  /opt/dnd-manager/.venv/bin/flask --app /opt/dnd-manager/app.py init-db
```

## 3. Installer le service

```bash
sudo cp deploy/dnd-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dnd-manager
curl http://127.0.0.1:8000/health
```

La réponse attendue est `{"status":"ok"}`.

## 4. Configurer HTTPS

Installer Nginx et Certbot, obtenir le certificat pour `dnd.sunitro.de`, puis
copier `deploy/nginx-dnd.sunitro.de.conf` dans
`/etc/nginx/sites-available/dnd.sunitro.de`.

Après activation du site :

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Vérifier ensuite :

```bash
curl -I https://dnd.sunitro.de/health
```

## 5. Activer les sauvegardes

```bash
sudo cp deploy/dnd-manager-backup.service /etc/systemd/system/
sudo cp deploy/dnd-manager-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dnd-manager-backup.timer
sudo systemctl start dnd-manager-backup.service
sudo systemctl status dnd-manager-backup.service
```

## Mise à jour

1. lancer une sauvegarde ;
2. copier la nouvelle version dans `/opt/dnd-manager` ;
3. installer `requirements.txt` ;
4. exécuter `flask --app app.py init-db` avec l'environnement de production ;
5. redémarrer avec `sudo systemctl restart dnd-manager` ;
6. vérifier `/health` et les journaux systemd.

## Retour arrière

Arrêter d'abord le service :

```bash
sudo systemctl stop dnd-manager
```

Restaurer ensuite une sauvegarde vérifiée :

```bash
sudo -u dnd-manager /opt/dnd-manager/.venv/bin/python \
  /opt/dnd-manager/scripts/restore.py \
  /var/backups/dnd-manager/dnd-manager-DATE.sqlite3 \
  /var/lib/dnd-manager/dnd-manager.sqlite3 \
  --force
sudo systemctl start dnd-manager
```

Terminer par `curl https://dnd.sunitro.de/health`.
