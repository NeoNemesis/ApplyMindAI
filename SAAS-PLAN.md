# ApplyMind AI — SaaS Transformation Plan
**Datum:** 2026-05-31  
**Mål:** Omvandla lokal enkeltänkt verktyg → multi-tenant webbapplikation  
**Domain:** [din-domän].se (konfigureras i fas 5)

---

## Executive Summary

ApplyMind AI transformeras från ett lokalt Python-script till en produktionsklar SaaS-plattform där:
- **Administratören** (du) skapar konton åt användare
- **Användare** loggar in och jobbar med sina egna CV:n, brev och jobbsökningar
- All data är isolerad per användare — ingen ser andras information
- En polerad landningssida + inloggningssida möter nya besökare
- Systemet är redo för deployment på valfri server med SSL

---

## Tekniska beslut (låsta)

| Komponent | Val | Motivering |
|-----------|-----|-----------|
| Auth | Flask-Login | Session-baserad, perfekt för webb-app (inte API) |
| Lösenord | Argon2id (argon2-cffi) | OWASP/NIST 2026 standard, bcrypt är utdaterat |
| Databas | SQLite (dev) → PostgreSQL (prod) | SQLAlchemy gör migrering till 1 konfigurationsrad |
| Schema-migration | Flask-Migrate + Alembic | Versionshantering av DB från dag 1 |
| Fillagring | `instance/uploads/user_{id}/` | Flask's inbyggda instansmapp, förhindrar path traversal |
| Analytics | Plausible (self-hosted) | GDPR-safe, ingen Google Analytics |
| Forms | Flask-WTF + CSRF | Skyddar alla formulär automatiskt |
| Cookies/GDPR | Cookie-banner med granulär kontroll | Swedish IMY krav, equal-prominence accept/reject |

---

## Databasschema

```sql
-- Användare
CREATE TABLE user (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT UNIQUE NOT NULL,
  email         TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,          -- Argon2id
  role          TEXT DEFAULT 'user',    -- 'admin' | 'user'
  is_active     BOOLEAN DEFAULT TRUE,
  created_at    TIMESTAMP DEFAULT NOW(),
  last_login    TIMESTAMP,
  -- Personliga inställningar (JSON)
  linkedin_email    TEXT,
  linkedin_password TEXT,               -- krypterad med app secret
  llm_provider      TEXT DEFAULT 'openai',
  llm_model         TEXT DEFAULT 'gpt-4o-mini',
  llm_api_key       TEXT,              -- krypterad
  language          TEXT DEFAULT 'sv'
);

-- Jobbansökningar (kopplade till användare)
CREATE TABLE job_application (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER REFERENCES user(id) ON DELETE CASCADE,
  folder     TEXT NOT NULL,            -- relativ sökväg under user dir
  title      TEXT,
  company    TEXT,
  location   TEXT,
  url        TEXT,
  date       DATE,
  has_cv     BOOLEAN DEFAULT FALSE,
  has_letter BOOLEAN DEFAULT FALSE,
  ats_score  INTEGER,
  tracker_status TEXT DEFAULT 'Redo att söka',
  created_at TIMESTAMP DEFAULT NOW()
);

-- Sessions (hanteras av Flask-Login, lagras i server-side sessions)
-- Cookie: session_id → server minne (eller Redis för produktion)

-- Audit log (admin-spårning)
CREATE TABLE audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  admin_id   INTEGER REFERENCES user(id),
  action     TEXT,                     -- 'create_user', 'delete_user', etc.
  target_id  INTEGER,
  timestamp  TIMESTAMP DEFAULT NOW()
);
```

---

## Filstruktur per användare

```
instance/
  uploads/
    user_1/                    ← Admin (Victor)
      data/
        plain_text_resume.yaml
        work_preferences.yaml
        email_config.yaml
        profile.png
        reference_cv.txt
        reference_cover_letter.txt
      output/
        Job_001_.../
          CV_xxx.pdf
          Brev_xxx.pdf
    user_2/                    ← Annan användare
      data/
      output/
```

---

## Fas 1: Auth + Databas (Sprint 1 — 1 session)

### Nya paket
```
flask-login==0.6.3
flask-sqlalchemy==3.1.1
flask-migrate==4.0.7
flask-wtf==1.2.1
argon2-cffi==23.1.0
cryptography==42.0.5       ← för kryptering av LinkedIn-lösenord
```

### Vad byggs
1. **`models.py`** — User-modell med SQLAlchemy
2. **`auth.py`** — Blueprint: `/login`, `/logout`, `@login_required`
3. **`admin.py`** — Blueprint: `/admin/users`, `/admin/users/create`, `/admin/users/toggle`
4. **`db.py`** — DB-initiering, Flask-Migrate setup
5. **Migrera `web_app.py`** — Alla routes wrappas med `@login_required`
6. **Filsökvägar** — `get_user_data_dir(user_id)` ersätter hårdkodad `data_folder/`

### Säkerhet
- CSRF-skydd på alla POST-formulär (Flask-WTF)
- Rate limiting på `/login` (5 försök/minut)
- Session timeout: 8 timmar aktiv, 30 dagar "kom ihåg mig"
- Secure + HttpOnly cookies
- Argon2id: memory=64MB, iterations=3, parallelism=1

---

## Fas 2: Per-användar dataisolering (Sprint 2 — 1 session)

### Princip
Varje funktion som idag läser från `data_folder/` ska istället läsa från `get_user_data_dir(current_user.id)`.

### Ändringar i web_app.py
```python
# FÖRE
DATA_DIR = Path("data_folder")

# EFTER  
def get_user_data_dir(user_id: int) -> Path:
    path = Path(app.instance_path) / "uploads" / f"user_{user_id}" / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_user_output_dir(user_id: int) -> Path:
    path = Path(app.instance_path) / "uploads" / f"user_{user_id}" / "output"
    path.mkdir(parents=True, exist_ok=True)
    return path
```

### Routes som påverkas
- `/cv/save` → sparar till user-specifik YAML
- `/cover-letter/save` → sparar till user-specifik fil
- `/search/run` → söker med user-specifika inställningar
- `/jobs` → listar BARA inloggad users ansökningar
- `/tracker` → visar BARA inloggad users kanban
- `/download/<path>` → validerar att användaren äger filen

---

## Fas 3: Landningssida + Inloggningssida (Sprint 3 — 1 session)

### Landningssida (`/`)
Ny route som visar landningssida för ej inloggade. Inloggade redirectas till `/dashboard`.

**Design brief:**
- **Stack:** HTML + Tailwind CDN (fristående från Flask-appen, enkel)
- **Stil:** Dark mode, grön accent (#4AE54A), Plus Jakarta Sans
- **Känsla:** Professionellt SaaS-verktyg — inte startup-fluff

**Sektioner:**
1. **Hero** — "Automatisera dina jobbansökningar med AI" + CTA "Logga in"
2. **Hur det fungerar** — 3 steg: Ladda upp CV → Sök jobb → Ladda ner ansökan
3. **Features** — Bento-grid: AI-matchning, auto-brev, ATS-optimering, kanban-spårare
4. **Tech stack** — "Drivs av GPT-4o, Claude, Gemini"
5. **Footer** — GDPR-info, integritetspolicy, cookiepolicy

**SEO (landningssida):**
```html
<title>ApplyMind AI — Automatisera Jobbansökningar med AI | Sverige</title>
<meta name="description" content="Sök hundratals jobb automatiskt med AI-genererade CV och personliga brev. Spara timmar per ansökan. Stöd för Indeed, Arbetsförmedlingen och Jobtech.">
<meta property="og:image" content="/static/og-image.png">  <!-- 1200x630px -->
<link rel="canonical" href="https://din-domän.se/">

<!-- Structured Data -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "ApplyMind AI",
  "applicationCategory": "BusinessApplication",
  "operatingSystem": "Web",
  "offers": {"@type": "Offer", "price": "0"},
  "description": "AI-driven jobbansökningsautomatisering för svenska jobbsökare"
}
</script>
```

### Inloggningssida (`/login`)
- Minimalistisk, centrerad, dark mode
- Logo + "ApplyMind AI" rubrik
- Email + lösenord + "Kom ihåg mig"
- "Glömt lösenord?" (skickar email, fas 4)
- Ingen "Skapa konto" — kontakta admin-text istället
- Flash-meddelanden för fel (röd border, skaka animation)
- Rate limiting visas som nedräkning

### Cookie-banner
- Visas första besöket för alla
- "Nödvändiga" alltid ON, kan ej stängas av
- "Analytics" (Plausible) — OFF by default
- Equal-prominence "Acceptera alla" / "Avvisa alla"
- Länk till integritetspolicysida

---

## Fas 4: Admin-panel (Sprint 4 — 1 session)

### Routes (endast `role='admin'`)
```
GET  /admin                    → Dashboard: antal users, aktivitet
GET  /admin/users              → Lista alla användare
POST /admin/users/create       → Skapa nytt konto (email + lösenord)
POST /admin/users/{id}/toggle  → Aktivera/inaktivera konto
POST /admin/users/{id}/reset   → Skicka lösenordsåterställning
GET  /admin/users/{id}/data    → Se användarens data (audit-loggat)
POST /admin/users/{id}/delete  → Radera konto + all data
```

### Admin-panel design
- Separat minimal layout (inte landningssidans layout)
- Tabell med: Namn, E-post, Skapad, Senast inloggad, Status, Åtgärder
- Modal för skapa användare
- Audit log-vy: Vem gjorde vad när

---

## Fas 5: Deployment (Sprint 5 — 1 session)

### Serverarkitektur
```
Internet → Nginx (SSL/TLS) → Gunicorn (Flask) → SQLite/PostgreSQL
                           → /static (Nginx serverar direkt)
                           → instance/uploads/ (skyddad av Nginx)
```

### Docker-compose (produktion)
```yaml
version: '3.8'
services:
  web:
    build: .
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_URL=postgresql://...
      - FLASK_ENV=production
    volumes:
      - uploads:/app/instance/uploads
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - /etc/letsencrypt:/etc/letsencrypt
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_DB=applymind
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
```

### Nginx-config (SSL + säkerhet)
```nginx
server {
    listen 443 ssl;
    server_name din-domän.se;
    
    ssl_certificate /etc/letsencrypt/live/din-domän.se/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/din-domän.se/privkey.pem;
    
    # Säkerhetsheaders
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'";
    
    # Blockera direkt åtkomst till uploads
    location /instance/ { return 403; }
    
    location / { proxy_pass http://web:5000; }
    location /static/ { alias /app/static/; expires 1y; }
}
```

### Checklista inför deploy
- [ ] `SECRET_KEY` i miljövariabler (64-byte random)
- [ ] `SESSION_COOKIE_SECURE=True`
- [ ] `SESSION_COOKIE_HTTPONLY=True`
- [ ] `SESSION_COOKIE_SAMESITE='Lax'`
- [ ] PostgreSQL-lösenord i `.env` (gitignorerad)
- [ ] Letsencrypt SSL (certbot auto-renew)
- [ ] `instance/uploads/` utanför git (`.gitignore`)
- [ ] Admin-lösenord byts vid första deploy
- [ ] Backup-cron för PostgreSQL (dagligen)

---

## Design-plan per sida

### Verktyg som används (i ordning)
1. **ui-ux-pro-max** — Designsystem + färgpalett per sida
2. **Stitch** (MCP) — Wireframes för landningssida
3. **21st.dev Magic** (MCP) — Sök klara komponenter (hero, feature-grid, pricing)
4. **animotion** (MCP) — Scroll-animationer, hover-effekter
5. **nano-banana-2** (MCP) — Hero-bild, OG-bild (1200x630)
6. **design-taste-frontend** (skill) — Anti-slop check på landningssidan
7. **impeccable** (skill) — A11y + performance audit

### Per sida
| Sida | Prioritet | Verktyg |
|------|-----------|---------|
| Landningssida | ⭐⭐⭐ | Stitch + 21st.dev + nano-banana |
| Inloggningssida | ⭐⭐⭐ | 21st.dev + animotion |
| Dashboard (befintlig) | ⭐⭐ | Bento grid (klar) |
| Admin-panel | ⭐⭐ | ui-ux-pro-max |
| CV-editor | ⭐ | Befintlig (refactor) |

---

## Tidplan

| Fas | Innehåll | Estimat |
|-----|----------|---------|
| **1** | Auth + DB + modeller + login | 1 session |
| **2** | Per-user dataisolering i alla routes | 1 session |
| **3** | Landningssida + inloggningssida + cookies | 1 session |
| **4** | Admin-panel (skapa/hantera users) | 1 session |
| **5** | Docker + nginx + SSL + deploy | 1 session |
| **6** | Testing + SEO + polish | 1 session |
| **Totalt** | | **6 sessioner** |

---

## Nästa steg — Fas 1 börjar med

```bash
pip install flask-login flask-sqlalchemy flask-migrate flask-wtf argon2-cffi cryptography
```

Sedan:
1. Skapa `models.py` med User-modell
2. Skapa `auth.py` blueprint (login/logout)
3. Initiera DB och skapa första admin-kontot
4. Wappa alla befintliga routes med `@login_required`
5. Testa att inloggning fungerar lokalt

---

## Säkerhetsnivå (målbild)

| Kategori | Krav | Status efter fas 1-5 |
|----------|------|----------------------|
| Auth | Argon2id lösenord | ✅ |
| Sessions | Secure HttpOnly cookies | ✅ |
| CSRF | Flask-WTF på alla POST | ✅ |
| Rate limiting | 5 försök/min på login | ✅ |
| File access | Validering att user äger filen | ✅ |
| Data isolation | Separat dir per user | ✅ |
| Transport | HTTPS/TLS 1.3 | ✅ |
| Headers | CSP, X-Frame, HSTS | ✅ |
| GDPR | Cookie-banner + integritetspolicy | ✅ |
| Audit | Loggar admin-åtgärder | ✅ |
