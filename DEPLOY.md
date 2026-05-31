# Deploy — vilchesapp.com på Hetzner 46.62.249.87

## Förutsättningar
- Server: Hetzner 46.62.249.87 (samma som Taskit)
- Docker + Docker Compose installerat
- Nginx installerat (delad med Taskit)
- Domän vilchesapp.com pekar på 46.62.249.87

## Steg 1: Ladda upp koden

```bash
# Från din lokala dator — pusha till GitHub
git add .
git commit -m "feat: SaaS auth + multi-user"
git push origin main

# På servern
ssh root@46.62.249.87
cd /opt
git clone https://github.com/DITT-REPO/applymind-ai.git
cd applymind-ai
```

## Steg 2: Konfigurera miljövariabler

```bash
cp .env.production.example .env.production
nano .env.production
# Fyll i: FLASK_SECRET, DATABASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD
```

Generera stark secret:
```bash
openssl rand -hex 32
```

## Steg 3: Starta appen

```bash
docker compose up -d --build
docker compose logs -f   # Verifiera att den startar
```

## Steg 4: Skapa admin-konto

```bash
docker compose exec applymind-web python init_admin.py
```

## Steg 5: Nginx + SSL

```bash
# Kopiera nginx-konfig
cp nginx-vilchesapp.conf /etc/nginx/sites-available/vilchesapp.com
ln -s /etc/nginx/sites-available/vilchesapp.com /etc/nginx/sites-enabled/

# Testa konfigurationen
nginx -t

# SSL-certifikat med certbot
certbot --nginx -d vilchesapp.com -d www.vilchesapp.com

# Starta om nginx
systemctl reload nginx
```

## Steg 6: Verifiera

```bash
curl -I https://vilchesapp.com/auth/login
# Ska svara: HTTP/2 200
```

## Backup

```bash
# Daglig backup av uploads (lägg i crontab)
0 3 * * * docker run --rm -v applymind-uploads:/data -v /opt/backups:/backup \
  alpine tar czf /backup/applymind-uploads-$(date +\%Y\%m\%d).tar.gz /data
```

## Uppdatera appen

```bash
cd /opt/applymind-ai
git pull origin main
docker compose up -d --build
```
