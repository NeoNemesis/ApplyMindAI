#!/usr/bin/env python3
"""
Skapar databasen och ett admin-konto.
Kör EN gång vid initial setup:

    python init_admin.py

Eller med anpassade värden:
    ADMIN_EMAIL=din@epost.se ADMIN_PASSWORD=hemligt python init_admin.py
"""
import os
import sys
from pathlib import Path

# Se till att vi kan importera appen
sys.path.insert(0, str(Path(__file__).parent))

from web_app import app
from models import db, User

def create_admin():
    email    = os.environ.get('ADMIN_EMAIL',    'admin@applymind.local')
    username = os.environ.get('ADMIN_USERNAME', 'admin')
    password = os.environ.get('ADMIN_PASSWORD', 'AdminChangeMe2026!')

    with app.app_context():
        Path(app.instance_path).mkdir(parents=True, exist_ok=True)
        db.create_all()
        print("✅ Databas initierad.")

        existing = User.query.filter_by(email=email).first()
        if existing:
            print(f"⚠️  Admin-konto finns redan: {email}")
            return

        admin = User(
            username = username,
            email    = email,
            role     = 'admin',
            is_active = True,
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()

        print(f"\n✅ Admin-konto skapat!")
        print(f"   E-post:      {email}")
        print(f"   Användarnamn:{username}")
        print(f"   Lösenord:    {password}")
        print(f"\n⚠️  Byt lösenord direkt vid första inloggning!")
        print(f"   Starta appen: python web_app.py")
        print(f"   Öppna:        http://localhost:5000/auth/login\n")

if __name__ == '__main__':
    create_admin()
