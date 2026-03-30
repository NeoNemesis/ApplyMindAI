#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ ApplyMind AI — Jobbsöknings- och ansökningssystem
======================================================
Kombinerar alla funktioner från tidigare script i ett enda kraftfullt verktyg

FUNKTIONER:
-----------
✅ Sök jobb på LinkedIn, Indeed, Arbetsförmedlingen
✅ Välj vilka platformar du vill söka på
✅ Välj antal jobb att söka
✅ Automatisk jobbfiltrering baserat på plats och IT-kompetens
✅ Genererar jobbanpassade CV med valt design
✅ Genererar jobbanpassade personliga brev
✅ Sparar dokument i strukturerade mappar
✅ Skapar job_info filer med ansökningsinstruktioner
✅ Undviker dubletter (sparar processade jobb)

ANVÄNDNING:
-----------
python job_master.py

Skapad av: Victor Vilches
Datum: 2026-02-10
Version: 1.0 MASTER
"""

import os
import sys
import json
import time
import base64
import re
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from dotenv import load_dotenv

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

# Import AIHawk modules
from src.resume_schemas.resume import Resume
from src.libs.resume_and_cover_builder.moderndesign1.modern_facade import ModernDesign1Facade
from src.libs.resume_and_cover_builder.moderndesign1.modern_style_manager import ModernDesign1StyleManager
from src.libs.resume_and_cover_builder.moderndesign1.modern_resume_generator import ModernDesign1ResumeGenerator

# Browser pool support
try:
    from src.utils.browser_pool import get_browser, cleanup_browser
    BROWSER_POOL_AVAILABLE = True
except ImportError:
    from src.utils.chrome_utils import init_browser
    BROWSER_POOL_AVAILABLE = False


class JobMaster:
    """Ultimat jobbsöknings- och ansökningssystem"""

    # IT-jobbkategorier baserat på ditt CV
    IT_JOB_CATEGORIES = {
        'systemutveckling': [
            "Systemutvecklare", "System Developer", "Fullstack Developer",
            "Full Stack Developer", "Software Developer", "Software Engineer"
        ],
        'frontend': [
            "Frontend Developer", "Frontend utvecklare", "React Developer",
            "JavaScript Developer", "Vue Developer", "Angular Developer"
        ],
        'backend': [
            "Backend Developer", "Backend utvecklare", "Java Developer",
            ".NET utvecklare", "Python Developer", "Node.js Developer"
        ],
        'webbutveckling': [
            "Webbutvecklare", "Web Developer", "Webb-utvecklare"
        ],
        'it_generellt': [
            "IT-utvecklare", "IT Developer", "Mjukvaruutvecklare",
            "DevOps Engineer", "IT-konsult"
        ]
    }

    # Exkluderade nyckelord (för avancerade roller)
    EXCLUDED_KEYWORDS = [
        'senior', 'lead', 'principal', 'architect', 'chef', 'manager',
        'director', 'head of', 'tech lead', 'team lead', '10+ years',
        '10 years', '8+ years', '5+ years experience'
    ]

    # Föredragna nyckelord (mellannivå och junior)
    PREFERRED_KEYWORDS = [
        'junior', 'utvecklare', 'developer', 'trainee', 'graduate',
        'entry level', 'nyexaminerad', 'starter'
    ]

    # Accepterade platser (Uppsala, södra Stockholm, Enköping, Remote)
    ACCEPTED_LOCATIONS = [
        # Uppsala-området
        'uppsala', 'enköping', 'knivsta', 'håbo',
        # Stockholm (södra och centrala)
        'stockholm', 'södermalm', 'kungsholmen', 'östermalm', 'vasastan',
        'gamla stan', 'norrmalm', 'bromma', 'hägersten', 'farsta',
        'enskede', 'skärholmen', 'älvsjö', 'solna', 'sundbyberg',
        # Remote
        'på distans', 'remote', 'fjärr', 'distans', 'hemarbete'
    ]

    # Exkluderade platser (för långt bort)
    EXCLUDED_LOCATIONS = [
        'göteborg', 'malmö', 'umeå', 'luleå', 'kiruna', 'västerås',
        'örebro', 'norrland', 'norrbotten', 'latinamerika', 'nordamerika'
    ]

    def __init__(self):
        """Initialisera Job Master"""
        self.driver = None
        self.resume_object = None
        self.modern_facade = None
        self.api_key = os.getenv('OPENAI_API_KEY')

        # Base directory - resolve to script's directory
        self.script_dir = Path(__file__).parent.absolute()

        # Output directories
        self.base_output_dir = self.script_dir / 'data_folder' / 'output' / 'job_master'
        self.base_output_dir.mkdir(parents=True, exist_ok=True)

        # Tracking files
        self.processed_jobs_file = self.base_output_dir / 'processed_jobs.json'
        self.found_jobs_file = self.base_output_dir / 'found_jobs.json'

        # Load processed jobs
        self.processed_urls: Set[str] = set()
        self.load_processed_jobs()

    def load_processed_jobs(self):
        """Ladda redan processade jobb för att undvika dubletter"""
        if self.processed_jobs_file.exists():
            try:
                with open(self.processed_jobs_file, 'r', encoding='utf-8') as f:
                    processed = json.load(f)
                    self.processed_urls = set(job['url'] for job in processed)
                print(f"📋 Laddade {len(self.processed_urls)} redan processade jobb")
            except Exception as e:
                print(f"⚠️  Kunde inte ladda processade jobb: {e}")
                self.processed_urls = set()

    def save_processed_job(self, job: Dict):
        """Spara ett processat jobb"""
        self.processed_urls.add(job['url'])

        # Load existing
        existing = []
        if self.processed_jobs_file.exists():
            try:
                with open(self.processed_jobs_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except:
                existing = []

        # Add new job with timestamp
        job['processed_date'] = datetime.now().isoformat()
        existing.append(job)

        # Save
        with open(self.processed_jobs_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

    def initialize(self):
        """Initialisera system"""
        print("\n" + "="*80)
        cv_design = os.getenv("CV_DESIGN", "design_01_minimal")
        print("⚡ ApplyMind AI — Jobbsöknings- och ansökningssystem")
        print("="*80)
        print("📍 Områden: Uppsala • Södra Stockholm • Enköping • Remote")
        print("💼 Plattformar: LinkedIn • Indeed • Arbetsförmedlingen")
        print(f"📄 Auto-generering: Jobbanpassade CV + Personliga Brev (Design: {cv_design})")
        print("="*80)

        # Ladda resume
        resume_yaml_path = self.script_dir / 'data_folder' / 'plain_text_resume.yaml'
        print(f"\n📖 Laddar CV från: {resume_yaml_path}")

        with open(resume_yaml_path, 'r', encoding='utf-8') as f:
            yaml_content = f.read()

        self.resume_object = Resume(yaml_content)
        print("✅ CV laddat")

        # Starta browser
        print("\n🌐 Startar browser...")
        if BROWSER_POOL_AVAILABLE:
            self.driver = get_browser()
            print("✅ Browser pool aktiverad (13x snabbare!)")
        else:
            self.driver = init_browser()
            print("✅ Browser startad")

        # Skapa dokumentgenereringsfacade
        style_manager = ModernDesign1StyleManager()
        style_manager.set_selected_style('Modern Design 1 - Default')  # style determined by design facade

        resume_generator = ModernDesign1ResumeGenerator()

        self.modern_facade = ModernDesign1Facade(
            api_key=self.api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=self.resume_object,
            output_path=self.base_output_dir
        )
        self.modern_facade.set_driver(self.driver)

        print("✅ ApplyMind AI dokumentgenereringssystem redo")
        print("="*80)

    def show_main_menu(self) -> Dict:
        """Visa huvudmeny och få användarens val"""
        print("\n" + "="*80)
        print("🔍 VÄLJ JOBBSÖKNINGSALTERNATIV")
        print("="*80)

        # Välj plattformar
        print("\n📌 STEG 1: Vilka plattformar vill du söka på?")
        print("  1. LinkedIn")
        print("  2. Indeed")
        print("  3. Arbetsförmedlingen")
        print("  4. Alla plattformar (Rekommenderat)")

        platform_choice = input("\nVälj (1-4) [4]: ").strip()

        platforms = {
            '1': ['linkedin'],
            '2': ['indeed'],
            '3': ['arbetsformedlingen'],
            '4': ['linkedin', 'indeed', 'arbetsformedlingen']
        }
        selected_platforms = platforms.get(platform_choice, ['linkedin', 'indeed', 'arbetsformedlingen'])

        # Välj antal jobb
        print("\n📌 STEG 2: Hur många jobb vill du söka?")
        print("  1. 5 jobb (snabbt)")
        print("  2. 10 jobb (rekommenderat)")
        print("  3. 20 jobb (omfattande)")
        print("  4. 30 jobb (maximalt)")

        job_count_choice = input("\nVälj (1-4) [2]: ").strip()

        job_counts = {
            '1': 5,
            '2': 10,
            '3': 20,
            '4': 30
        }
        max_jobs = job_counts.get(job_count_choice, 10)

        # Välj lägen
        print("\n📌 STEG 3: Välj körläge")
        print("  1. Automatisk (Genererar dokument för alla jobb)")
        print("  2. Interaktiv (Du väljer för varje jobb)")

        mode_choice = input("\nVälj (1-2) [1]: ").strip()
        auto_generate = mode_choice != '2'

        return {
            'platforms': selected_platforms,
            'max_jobs': max_jobs,
            'auto_generate': auto_generate
        }

    def is_suitable_level(self, job_title: str, job_description: str = "") -> bool:
        """Kontrollera om jobbet är på rätt nivå (inte senior)"""
        title_lower = job_title.lower()
        desc_lower = job_description.lower()
        combined = title_lower + " " + desc_lower

        # Exkludera senior/avancerade roller
        for keyword in self.EXCLUDED_KEYWORDS:
            if keyword in combined:
                return False

        # Om något föredraget nyckelord finns, acceptera direkt
        for keyword in self.PREFERRED_KEYWORDS:
            if keyword in combined:
                return True

        # Om inget exkluderat nyckelord finns, acceptera
        return True

    def is_local_job(self, location: str) -> bool:
        """Kontrollera om jobbet är i accepterad plats (dynamisk baserat på search_locations).
        ACCEPTED_LOCATIONS-konstanten behålls för bakåtkompatibilitet men används ej längre.
        """
        if not location:
            return False

        location_lower = location.lower()

        # Alltid acceptera remote- och distansjobb
        if 'remote' in location_lower or 'distans' in location_lower or 'fjärr' in location_lower:
            return True

        # Om inga sökortsplatser är satta — acceptera alla platser (failsafe)
        search_locs = getattr(self, 'search_locations', [])
        if not search_locs:
            return True

        # Kontrollera om platsen matchar någon av användarens valda platser (case-insensitive)
        for chosen in search_locs:
            if chosen.lower() in location_lower or location_lower in chosen.lower():
                return True

        return False

    # ------------------------------------------------------------------
    # LinkedIn cookie helpers
    # ------------------------------------------------------------------

    def _save_linkedin_cookies(self):
        """Spara LinkedIn-session cookies till fil för framtida inloggningar."""
        cookie_path = self.script_dir / 'data_folder' / 'linkedin_cookies.json'
        try:
            cookies = self.driver.get_cookies()
            with open(cookie_path, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, indent=2)
            print(f"🍪 LinkedIn-cookies sparade ({len(cookies)} cookies)")
        except Exception as e:
            print(f"⚠️  Kunde inte spara cookies: {e}")

    def _load_linkedin_cookies(self) -> bool:
        """Försök återställa LinkedIn-session från sparade cookies.
        Returnerar True om sidan laddas som inloggad, annars False."""
        cookie_path = self.script_dir / 'data_folder' / 'linkedin_cookies.json'
        if not cookie_path.exists():
            return False
        try:
            with open(cookie_path, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            # Måste navigera till domänen innan cookies läggs till
            self.driver.get("https://www.linkedin.com")
            time.sleep(2)
            for cookie in cookies:
                cookie.pop('sameSite', None)  # Chromedriver godkänner inte okända värden
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    continue
            # Navigera till feed och kontrollera om vi är inloggade
            self.driver.get("https://www.linkedin.com/feed/")
            time.sleep(3)
            url = self.driver.current_url
            if 'login' not in url and 'checkpoint' not in url and 'linkedin.com' in url:
                print("✅ LinkedIn-session återställd från cookies!")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Kunde inte ladda cookies: {e}")
            return False

    def login_to_linkedin(self) -> bool:
        """Logga in på LinkedIn. Försöker cookies först, faller tillbaka på lösenord."""
        print("\n🔐 LOGGAR IN PÅ LINKEDIN")
        print("="*80)

        # Steg 1: Försök cookie-inloggning
        print("🍪 Försöker återställa session från cookies...")
        if self._load_linkedin_cookies():
            return True
        print("   → Inga giltiga cookies, försöker med lösenord...")

        # Steg 2: Lösenordsinloggning
        email = os.getenv('LINKEDIN_EMAIL')
        password = os.getenv('LINKEDIN_PASSWORD')

        if not email or not password:
            print("❌ LinkedIn-uppgifter saknas i .env (LINKEDIN_EMAIL / LINKEDIN_PASSWORD)")
            return False

        try:
            self.driver.get("https://www.linkedin.com/login")
            time.sleep(2)

            email_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            email_field.send_keys(email)
            time.sleep(0.5)

            password_field = self.driver.find_element(By.ID, "password")
            password_field.send_keys(password)
            time.sleep(0.5)

            login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_button.click()
            time.sleep(5)

            current_url = self.driver.current_url
            if "checkpoint" in current_url or "challenge" in current_url:
                print("\n⚠️  LinkedIn kräver säkerhetsverifiering!")
                print("⏸️  Väntar 30 sekunder för manuell verifiering...")
                time.sleep(30)

            time.sleep(2)
            # Steg 3: Spara cookies så nästa start slipper lösenord
            self._save_linkedin_cookies()
            print("✅ Inloggad på LinkedIn!")
            return True

        except Exception as e:
            print(f"❌ Fel vid inloggning: {str(e)}")
            return False

    def search_linkedin_jobs(self, max_jobs: int) -> List[Dict]:
        """Sök jobb på LinkedIn"""
        print(f"\n🔍 SÖKER JOBB PÅ LINKEDIN (max {max_jobs})")
        print("="*80)

        all_jobs = []
        seen_urls = set()

        # Generera sökningar baserat på jobbkategorier
        searches = []
        for location in ['Uppsala', 'Stockholm', 'Enköping']:
            for category_jobs in self.IT_JOB_CATEGORIES.values():
                for job_title in category_jobs[:2]:  # Ta 2 jobb per kategori
                    searches.append({
                        'title': job_title,
                        'location': f'{location}, Sverige'
                    })

        # Begränsa antal sökningar
        searches = searches[:15]

        for i, search in enumerate(searches, 1):
            if len(all_jobs) >= max_jobs:
                break

            print(f"\n[{i}/{len(searches)}] 🔍 {search['title']} i {search['location']}")

            try:
                search_url = f"https://www.linkedin.com/jobs/search/?keywords={search['title']}&location={search['location']}&f_TPR=r86400"
                self.driver.get(search_url)
                time.sleep(3)

                # Scrolla för att ladda mer
                for scroll in range(2):
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.5)

                # Hitta jobbkort
                job_cards = []
                selectors = [
                    "li.jobs-search-results__list-item",
                    "div.job-card-container",
                    "li.scaffold-layout__list-item"
                ]

                for selector in selectors:
                    try:
                        job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if job_cards:
                            print(f"   ✅ Hittade {len(job_cards)} jobbkort")
                            break
                    except:
                        continue

                if not job_cards:
                    print(f"   ⚠️  Inga jobbkort hittades")
                    continue

                # Extrahera jobb-information
                for card in job_cards[:10]:
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                        time.sleep(0.5)

                        # Extrahera titel
                        title = None
                        for sel in ["h3.base-search-card__title", "a.job-card-list__title", "h3"]:
                            try:
                                elem = card.find_element(By.CSS_SELECTOR, sel)
                                title = elem.text.strip()
                                if title and len(title) > 3:
                                    break
                            except:
                                continue

                        if not title:
                            continue

                        # Extrahera företag
                        company = "Okänt företag"
                        for sel in ["h4.base-search-card__subtitle", "a.job-card-container__company-name", "h4"]:
                            try:
                                elem = card.find_element(By.CSS_SELECTOR, sel)
                                company = elem.text.strip()
                                if company and len(company) > 2:
                                    break
                            except:
                                continue

                        # Extrahera plats
                        location = search['location']
                        for sel in ["span.job-search-card__location", "span.job-card-container__metadata-item"]:
                            try:
                                elem = card.find_element(By.CSS_SELECTOR, sel)
                                loc_text = elem.text.strip()
                                if loc_text and len(loc_text) > 2:
                                    location = loc_text
                                    break
                            except:
                                continue

                        # Filtrera lokala jobb
                        if not self.is_local_job(location):
                            continue

                        # Extrahera URL
                        url = None
                        for sel in ["a.base-card__full-link", "a.job-card-list__title", "a.job-card-container__link"]:
                            try:
                                elem = card.find_element(By.CSS_SELECTOR, sel)
                                url = elem.get_attribute('href')
                                if url and 'linkedin.com/jobs' in url:
                                    if '?' in url:
                                        url = url.split('?')[0]
                                    break
                            except:
                                continue

                        if not url or url in seen_urls or url in self.processed_urls:
                            continue

                        seen_urls.add(url)

                        job = {
                            'title': title,
                            'company': company,
                            'location': location,
                            'url': url,
                            'source': 'LinkedIn',
                            'search_query': f"{search['title']} i {search['location']}",
                            'found_date': datetime.now().isoformat()
                        }

                        all_jobs.append(job)
                        print(f"   ✅ {title} @ {company} - {location}")

                    except Exception as e:
                        continue

            except Exception as e:
                print(f"   ❌ Fel: {str(e)}")
                continue

        print(f"\n📊 LinkedIn: {len(all_jobs)} lokala jobb hittade")
        return all_jobs

    def search_indeed_jobs(self, max_jobs: int) -> List[Dict]:
        """Sök jobb på Indeed - Uppsala + Södra Stockholm, 50 km radie"""
        print(f"\n🔍 SÖKER JOBB PÅ INDEED (max {max_jobs})")
        print("="*80)
        print("📍 Uppsala + Södra Stockholm (50 km radie)")
        print("💼 Jobbtyper: IT-utvecklare, IT-tekniker, Systemadministratör")
        print("="*80)

        all_jobs = []
        seen_urls = set()

        # Bygg sökningar dynamiskt från användarens valda positioner och platser
        searches = []
        for position in self.search_positions:
            for location in self.search_locations:
                searches.append({"keyword": position, "location": location})
        # Fallback om inga inställningar finns
        if not searches:
            searches = [
                {"keyword": "Systemutvecklare", "location": "Uppsala"},
                {"keyword": "IT-utvecklare", "location": "Uppsala"},
                {"keyword": "Junior utvecklare", "location": "Stockholm"},
            ]

        for search in searches:
            if len(all_jobs) >= max_jobs:
                break

            print(f"\n🔍 {search['keyword']} i {search['location']}")

            try:
                search_url = f"https://se.indeed.com/jobs?q={search['keyword']}&l={search['location']}&radius=50&sort=date"
                self.driver.get(search_url)
                time.sleep(3)

                # Hitta jobbkort
                job_cards = self.driver.find_elements(By.CLASS_NAME, 'job_seen_beacon')
                print(f"   📋 {len(job_cards)} jobbkort hittade")

                for card in job_cards[:10]:
                    try:
                        # Extrahera titel
                        try:
                            title_elem = card.find_element(By.CSS_SELECTOR, 'h2.jobTitle span')
                            title = title_elem.text.strip()
                        except:
                            title = "Okänd titel"

                        # Extrahera företag
                        try:
                            company_elem = card.find_element(By.CSS_SELECTOR, '[data-testid="company-name"]')
                            company = company_elem.text.strip()
                        except:
                            company = "Okänt företag"

                        # Extrahera plats
                        try:
                            location_elem = card.find_element(By.CSS_SELECTOR, '[data-testid="text-location"]')
                            location = location_elem.text.strip()
                        except:
                            location = search['location']

                        # Filtrera lokala jobb
                        if not self.is_local_job(location):
                            continue

                        # Filtrera bort senior-roller
                        if not self.is_suitable_level(title):
                            print(f"   ⏭️  Hoppar över: {title} (för avancerad nivå)")
                            continue

                        # Extrahera URL
                        try:
                            link_elem = card.find_element(By.CSS_SELECTOR, 'h2.jobTitle a')
                            href = link_elem.get_attribute('href')
                            url = href if href.startswith('http') else f"https://se.indeed.com{href}"
                        except:
                            continue

                        if not url or url in seen_urls or url in self.processed_urls:
                            continue

                        seen_urls.add(url)

                        job = {
                            'title': title,
                            'company': company,
                            'location': location,
                            'url': url,
                            'source': 'Indeed',
                            'search_query': f"{search['keyword']} i {search['location']}",
                            'found_date': datetime.now().isoformat()
                        }

                        all_jobs.append(job)
                        print(f"   ✅ {title} @ {company} - {location}")

                    except Exception as e:
                        continue

            except Exception as e:
                print(f"   ❌ Fel: {str(e)}")
                continue

        print(f"\n📊 Indeed: {len(all_jobs)} lokala jobb hittade")
        return all_jobs

    def search_indeed_jobs_deep(self, max_jobs: int) -> List[Dict]:
        """Sök jobb på Indeed med DJUPARE sökning (letar igenom 30+ jobbkort istället för 10)"""
        print(f"\n🔍 SÖKER JOBB PÅ INDEED - DJUPARE SÖKNING (max {max_jobs})")
        print("="*80)
        print("📍 Uppsala + Södra Stockholm (50 km radie)")
        print("💼 Jobbtyper: IT-utvecklare, IT-tekniker, Systemadministratör")
        print("🔎 Söker genom 30+ jobbkort per sökning (skippar kända duplikat)")
        print("="*80)

        all_jobs = []
        seen_urls = set()

        searches = [
            {"keyword": "Systemutvecklare", "location": "Uppsala"},
            {"keyword": "IT-utvecklare", "location": "Uppsala"},
            {"keyword": "Webbutvecklare", "location": "Uppsala"},
            {"keyword": "Backend utvecklare", "location": "Uppsala"},
            {"keyword": "Frontend utvecklare", "location": "Uppsala"},
            {"keyword": "Fullstack utvecklare", "location": "Uppsala"},
        ]

        for search in searches:
            if len(all_jobs) >= max_jobs:
                break

            print(f"\n🔍 {search['keyword']} i {search['location']}")

            try:
                search_url = f"https://se.indeed.com/jobs?q={search['keyword']}&l={search['location']}&radius=50&sort=date"
                self.driver.get(search_url)
                time.sleep(3)

                # Hitta jobbkort - SÖKER IGENOM FLER (30 istället för 10)
                job_cards = self.driver.find_elements(By.CLASS_NAME, 'job_seen_beacon')
                print(f"   📋 {len(job_cards)} jobbkort hittade (kollar igenom 30 st)")

                # Kolla igenom FLER jobbkort för att hitta nya
                for card in job_cards[:30]:  # ÖKAD FRÅN 10 TILL 30
                    if len(all_jobs) >= max_jobs:
                        break

                    try:
                        # Extrahera titel
                        try:
                            title_elem = card.find_element(By.CSS_SELECTOR, 'h2.jobTitle span')
                            title = title_elem.text.strip()
                        except:
                            title = "Okänd titel"

                        # Extrahera företag
                        try:
                            company_elem = card.find_element(By.CSS_SELECTOR, '[data-testid="company-name"]')
                            company = company_elem.text.strip()
                        except:
                            company = "Okänt företag"

                        # Extrahera plats
                        try:
                            location_elem = card.find_element(By.CSS_SELECTOR, '[data-testid="text-location"]')
                            location = location_elem.text.strip()
                        except:
                            location = search['location']

                        # Filtrera lokala jobb
                        if not self.is_local_job(location):
                            continue

                        # Filtrera bort senior-roller
                        if not self.is_suitable_level(title):
                            print(f"   ⏭️  Hoppar över: {title} (för avancerad nivå)")
                            continue

                        # Extrahera URL
                        try:
                            link_elem = card.find_element(By.CSS_SELECTOR, 'h2.jobTitle a')
                            href = link_elem.get_attribute('href')
                            url = href if href.startswith('http') else f"https://se.indeed.com{href}"
                        except:
                            continue

                        # SKIPPA DUPLIKAT (både från denna session och tidigare processade)
                        if not url or url in seen_urls or url in self.processed_urls:
                            continue

                        seen_urls.add(url)

                        job = {
                            'title': title,
                            'company': company,
                            'location': location,
                            'url': url,
                            'source': 'Indeed',
                            'search_query': f"{search['keyword']} i {search['location']}",
                            'found_date': datetime.now().isoformat()
                        }

                        all_jobs.append(job)
                        print(f"   ✅ {title} @ {company} - {location}")

                    except Exception as e:
                        continue

            except Exception as e:
                print(f"   ❌ Fel: {str(e)}")
                continue

        print(f"\n📊 Indeed: {len(all_jobs)} nya lokala jobb hittade")
        return all_jobs

    def search_indeed_jobs_multipage(self, max_jobs: int, max_pages: int = 3) -> List[Dict]:
        """Sök jobb på Indeed över FLERA SIDOR (sida 1, 2, 3...) för att hitta nya jobb"""
        print(f"\n🔍 SÖKER JOBB PÅ INDEED - MULTI-SIDA SÖKNING (max {max_jobs})")
        print("="*80)
        print("📍 Uppsala + Södra Stockholm (50 km radie)")
        print("💼 Jobbtyper: IT-utvecklare, IT-tekniker, Systemadministratör")
        print(f"📄 Söker på sida 1-{max_pages} (skippar redan processade jobb)")
        print("="*80)

        all_jobs = []
        seen_urls = set()

        searches = [
            {"keyword": "it", "location": "Uppsala"},
            {"keyword": "utvecklare", "location": "Uppsala"},
            {"keyword": "developer", "location": "Uppsala"},
            {"keyword": "it", "location": "Stockholm"},
            {"keyword": "utvecklare", "location": "Stockholm"},
            {"keyword": "programmer", "location": "Stockholm"},
        ]

        for search in searches:
            if len(all_jobs) >= max_jobs:
                break

            print(f"\n🔍 {search['keyword']} i {search['location']}")

            # Sök på flera sidor
            for page in range(max_pages):
                if len(all_jobs) >= max_jobs:
                    break

                try:
                    # Indeed använder &start=0, &start=10, &start=20 för paginering
                    start = page * 10
                    search_url = f"https://se.indeed.com/jobs?q={search['keyword']}&l={search['location']}&radius=50&sort=date&start={start}"

                    print(f"   📄 Sida {page + 1} (start={start})")
                    self.driver.get(search_url)
                    time.sleep(5)  # Längre väntetid för att sidan ska ladda

                    # Scrolla ner för att ladda alla jobb (lazy loading)
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)

                    # Hitta jobbkort
                    job_cards = self.driver.find_elements(By.CLASS_NAME, 'job_seen_beacon')
                    print(f"   📋 {len(job_cards)} jobbkort hittade på denna sida")

                    page_jobs = 0
                    for card in job_cards:
                        if len(all_jobs) >= max_jobs:
                            break

                        try:
                            # Extrahera titel
                            try:
                                title_elem = card.find_element(By.CSS_SELECTOR, 'h2.jobTitle span')
                                title = title_elem.text.strip()
                            except:
                                continue

                            # Extrahera företag
                            try:
                                company_elem = card.find_element(By.CSS_SELECTOR, '[data-testid="company-name"]')
                                company = company_elem.text.strip()
                            except:
                                continue

                            # Extrahera plats
                            try:
                                location_elem = card.find_element(By.CSS_SELECTOR, '[data-testid="text-location"]')
                                location = location_elem.text.strip()
                            except:
                                location = search['location']

                            # Filtrera lokala jobb
                            if not self.is_local_job(location):
                                continue

                            # Filtrera bort senior-roller
                            if not self.is_suitable_level(title):
                                continue

                            # Extrahera URL
                            try:
                                link_elem = card.find_element(By.CSS_SELECTOR, 'h2.jobTitle a')
                                href = link_elem.get_attribute('href')
                                url = href if href.startswith('http') else f"https://se.indeed.com{href}"
                            except:
                                continue

                            # SKIPPA DUPLIKAT - både från denna session och tidigare processade
                            if not url or url in seen_urls or url in self.processed_urls:
                                continue

                            seen_urls.add(url)
                            page_jobs += 1

                            job = {
                                'title': title,
                                'company': company,
                                'location': location,
                                'url': url,
                                'source': 'Indeed',
                                'search_query': f"{search['keyword']} i {search['location']} (sida {page+1})",
                                'found_date': datetime.now().isoformat()
                            }

                            all_jobs.append(job)
                            print(f"   ✅ {title} @ {company} - {location}")

                        except Exception as e:
                            continue

                    print(f"   → {page_jobs} nya jobb från sida {page + 1}")

                except Exception as e:
                    print(f"   ❌ Fel på sida {page + 1}: {str(e)}")
                    continue

        print(f"\n📊 Indeed (multi-sida): {len(all_jobs)} nya lokala jobb hittade")
        return all_jobs

    def search_arbetsformedlingen_jobs(self, max_jobs: int) -> List[Dict]:
        """Sök jobb på Arbetsförmedlingen"""
        print(f"\n🔍 SÖKER JOBB PÅ ARBETSFÖRMEDLINGEN (max {max_jobs})")
        print("="*80)

        all_jobs = []
        seen_urls = set()

        import urllib.parse as _urlparse
        searches = []
        for position in self.search_positions[:3]:
            for location in self.search_locations[:3]:
                q = _urlparse.quote(position)
                l = _urlparse.quote(location)
                searches.append({
                    "location": location,
                    "keyword": position,
                    "url": f"https://arbetsformedlingen.se/platsbanken/annonser?q={q}&l={l}"
                })
        # Fallback om inga inställningar finns
        if not searches:
            searches = [
                {"location": "Uppsala", "keyword": "systemutvecklare",
                 "url": "https://arbetsformedlingen.se/platsbanken/annonser?q=systemutvecklare&l=Uppsala"},
            ]

        for search in searches:
            if len(all_jobs) >= max_jobs:
                break

            try:
                print(f"\n🔍 Söker i {search['location']}")
                self.driver.get(search['url'])
                time.sleep(3)

                # Scrolla
                for _ in range(2):
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)

                # Hitta jobbkort
                job_cards = []
                for selector in ["article", "div[class*='job']", "a[href*='/platsbanken/annonser/']"]:
                    try:
                        job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if job_cards and len(job_cards) > 2:
                            print(f"   ✅ Hittade {len(job_cards)} jobbkort")
                            break
                    except:
                        continue

                if not job_cards:
                    print(f"   ⚠️  Inga jobbkort hittades")
                    continue

                for card in job_cards[:10]:
                    try:
                        # Hitta länk
                        link_elem = card.find_element(By.TAG_NAME, "a")
                        url = link_elem.get_attribute('href')

                        if not url or 'arbetsformedlingen.se' not in url:
                            continue

                        if url in seen_urls or url in self.processed_urls:
                            continue

                        # Extrahera text
                        text = card.text.strip()
                        lines = text.split('\n')

                        title = lines[0] if lines else "Okänd titel"
                        company = lines[1] if len(lines) > 1 else "Okänt företag"
                        location = search['location']

                        if len(title) < 3:
                            continue

                        seen_urls.add(url)

                        job = {
                            'title': title,
                            'company': company,
                            'location': location,
                            'url': url,
                            'source': 'Arbetsförmedlingen',
                            'search_query': search['location'],
                            'found_date': datetime.now().isoformat()
                        }

                        all_jobs.append(job)
                        print(f"   ✅ {title} @ {company}")

                    except Exception as e:
                        continue

            except Exception as e:
                print(f"   ❌ Fel: {str(e)}")
                continue

        print(f"\n📊 Arbetsförmedlingen: {len(all_jobs)} jobb hittade")
        return all_jobs

    def search_jobs(self, platforms: List[str], max_jobs: int,
                    locations: List[str] = None,
                    positions: List[str] = None) -> List[Dict]:
        """Sök jobb på valda plattformar med användarens platser och jobbtitlar"""
        # Store user's search criteria for use by individual search methods
        self.search_locations = locations or ['Uppsala']
        self.search_positions = positions or ['Junior Systemutvecklare', 'Webbutvecklare']
        all_jobs = []

        # LinkedIn (kräver inloggning)
        if 'linkedin' in platforms:
            if self.login_to_linkedin():
                linkedin_jobs = self.search_linkedin_jobs(max_jobs)
                all_jobs.extend(linkedin_jobs)

        # Indeed
        if 'indeed' in platforms:
            indeed_jobs = self.search_indeed_jobs(max_jobs)
            all_jobs.extend(indeed_jobs)

        # Arbetsförmedlingen
        if 'arbetsformedlingen' in platforms:
            af_jobs = self.search_arbetsformedlingen_jobs(max_jobs)
            all_jobs.extend(af_jobs)

        # Jobtech API (Sveriges officiella jobbdatabas — ingen inloggning krävs)
        if 'jobtech' in platforms:
            jobtech_jobs = self.search_jobtech_jobs(max_jobs)
            all_jobs.extend(jobtech_jobs)

        # Begränsa till max_jobs
        all_jobs = all_jobs[:max_jobs]

        # Spara alla jobb
        if all_jobs:
            with open(self.found_jobs_file, 'w', encoding='utf-8') as f:
                json.dump(all_jobs, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Sparade {len(all_jobs)} jobb till: {self.found_jobs_file}")

        return all_jobs


    def search_jobtech_jobs(self, max_jobs: int) -> List[Dict]:
        """Sök via Jobtech API (Sveriges officiella jobbdatabas — ingen inloggning krävs)"""
        import urllib.request as _urllib_req
        import urllib.parse as _urllib_parse
        import json as _json_lib

        print(f"\n🔍 SÖKER VIA JOBTECH API (max {max_jobs})")
        print("=" * 80)

        all_jobs: List[Dict] = []
        seen_urls: set = set()

        for position in self.search_positions[:5]:
            if len(all_jobs) >= max_jobs:
                break
            try:
                q = _urllib_parse.quote(position)
                api_url = f"https://links.api.jobtechdev.se/joblinks?q={q}&limit=20"

                req = _urllib_req.Request(api_url, headers={
                    'Accept': 'application/json',
                    'User-Agent': 'ApplyMindAI/2.0',
                })
                with _urllib_req.urlopen(req, timeout=10) as resp:
                    data = _json_lib.loads(resp.read().decode())

                hits = data.get('hits', []) or data.get('jobs', []) or []

                for hit in hits:
                    if len(all_jobs) >= max_jobs:
                        break

                    url = hit.get('webpage_url') or hit.get('url', '')
                    title = hit.get('headline') or hit.get('title', 'Okänd titel')
                    employer = hit.get('employer', {})
                    company = (
                        employer.get('name', 'Okänt företag')
                        if isinstance(employer, dict)
                        else str(employer)
                    )
                    workplace = hit.get('workplace_address', {})
                    location = (
                        workplace.get('municipality', '')
                        if isinstance(workplace, dict)
                        else ''
                    )

                    if not url or url in seen_urls or url in self.processed_urls:
                        continue

                    # Location filter — accept when no municipality provided
                    if location and not self.is_local_job(location):
                        continue

                    # Level filter
                    if not self.is_suitable_level(title):
                        print(f"   ⏭️  Hoppar över: {title} (för avancerad nivå)")
                        continue

                    seen_urls.add(url)
                    all_jobs.append({
                        'title': title,
                        'company': company,
                        'location': location or 'Sverige',
                        'url': url,
                        'source': 'Jobtech',
                        'search_query': position,
                        'found_date': datetime.now().isoformat(),
                    })
                    print(f"   ✅ {title} @ {company} - {location}")

            except Exception as e:
                print(f"   ⚠️  Jobtech-fel för '{position}': {e}")
                continue

        print(f"\n📊 Jobtech: {len(all_jobs)} jobb hittade")
        return all_jobs

    def quick_ats_score(self, job_description: str, threshold: int) -> tuple:
        """Snabb ATS-bedömning via LLM innan dokumentgenerering.
        Returnerar (score: int, reasoning: str).
        Vid fel returneras (100, 'fallback') så jobbet inte missas."""
        try:
            api_key = os.getenv('OPENAI_API_KEY', '')
            if not api_key:
                return (100, 'Ingen API-nyckel — hoppar över filter')

            # Bygg kompakt CV-sammanfattning
            pi = getattr(self.resume_object, 'personal_information', {}) or {}
            skills = getattr(self.resume_object, 'technical_skills', {}) or {}
            exp = getattr(self.resume_object, 'experience_details', []) or []
            skill_list = []
            for v in (skills.values() if hasattr(skills, 'values') else []):
                if isinstance(v, list):
                    skill_list.extend(v)
            cv_summary = (
                f"Skills: {', '.join(skill_list[:20])}\n"
                f"Experience: {len(exp)} positions\n"
            )

            import openai
            client = openai.OpenAI(api_key=api_key)
            prompt = (
                f"Rate this CV against the job description. Reply with ONLY:\n"
                f"Score: <0-100>\nReasoning: <one sentence>\n\n"
                f"CV:\n{cv_summary}\n\n"
                f"Job (first 1500 chars):\n{job_description[:1500]}"
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0,
            )
            text = resp.choices[0].message.content or ''
            import re
            m = re.search(r'Score:\s*(\d+)', text)
            score = int(m.group(1)) if m else 100
            reasoning = re.sub(r'Score:\s*\d+\s*', '', text).replace('Reasoning:', '').strip()
            return (min(100, max(0, score)), reasoning)
        except Exception as e:
            return (100, f'Fel i ATS-check: {e}')

    def attempt_auto_apply(self, job: Dict, job_folder) -> str:
        """Försöker auto-ansöka för Indeed och AF-jobb.
        Returnerar: 'submitted', 'prefilled', 'skipped (<orsak>)'"""
        source = job.get('source', '')
        dry_run = os.getenv('AUTO_APPLY_DRY_RUN', 'true').lower() != 'false'

        # Hitta CV-filen i jobbmappen
        cv_files = list(job_folder.glob('CV_*.pdf'))
        cover_files = list(job_folder.glob('Personligt_Brev_*.pdf'))
        if not cv_files or not cover_files:
            return 'skipped (dokument saknas)'

        cv_path = cv_files[0]
        cover_path = cover_files[0]

        try:
            if 'Indeed' in source or 'indeed' in source.lower():
                return self._auto_apply_indeed(job, cv_path, cover_path, dry_run)
            elif 'Arbetsförmedlingen' in source or 'af' in source.lower():
                return self._auto_apply_af(job, cv_path, cover_path, dry_run)
            else:
                return f'skipped (plattformen {source} stöds ej)'
        except Exception as e:
            return f'skipped (fel: {str(e)[:80]})'

    def _auto_apply_indeed(self, job: Dict, cv_path, cover_path, dry_run: bool) -> str:
        """Auto-ansök på Indeed via Easy Apply."""
        self.driver.get(job['url'])
        time.sleep(3)

        # Leta efter Easy Apply-knapp
        easy_apply_selectors = [
            "button[aria-label*='Apply']",
            "button[class*='apply']",
            "[data-testid='applyButton']",
            "a[class*='apply']",
        ]
        apply_btn = None
        for sel in easy_apply_selectors:
            btns = self.driver.find_elements(By.CSS_SELECTOR, sel)
            if btns:
                apply_btn = btns[0]
                break

        if not apply_btn:
            return 'skipped (ingen Easy Apply-knapp hittad)'

        # Kontrollera att det är en Indeed-intern ansökan (inte extern redirect)
        href = apply_btn.get_attribute('href') or ''
        if href and 'indeed.com' not in href and href.startswith('http'):
            return 'skipped (extern ansökan)'

        apply_btn.click()
        time.sleep(3)

        current_url = self.driver.current_url
        if 'indeed.com' not in current_url:
            return 'skipped (redirectad till extern sida)'

        # Fyll i namn och e-post om fälten finns
        pi = getattr(self.resume_object, 'personal_information', {}) or {}
        name = f"{pi.get('name', '')} {pi.get('surname', '')}".strip()
        email = pi.get('email', '')

        for field_id in ['applicant.name', 'name', 'fullName']:
            fields = self.driver.find_elements(By.CSS_SELECTOR, f"input[name='{field_id}'], input[id='{field_id}']")
            if fields and name:
                fields[0].clear()
                fields[0].send_keys(name)
                break

        for field_id in ['applicant.email', 'email']:
            fields = self.driver.find_elements(By.CSS_SELECTOR, f"input[name='{field_id}'], input[id='{field_id}']")
            if fields and email:
                fields[0].clear()
                fields[0].send_keys(email)
                break

        # Ladda upp CV
        file_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        if file_inputs:
            file_inputs[0].send_keys(str(cv_path.absolute()))
            time.sleep(2)

        if dry_run:
            return 'prefilled (dry-run — skickades ej)'

        # Klicka submit
        submit_btns = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], button[aria-label*='Submit'], button[aria-label*='Skicka']")
        if submit_btns:
            submit_btns[0].click()
            time.sleep(3)
            return 'submitted ✅'

        return 'prefilled (submit-knapp ej hittad)'

    def _auto_apply_af(self, job: Dict, cv_path, cover_path, dry_run: bool) -> str:
        """Auto-ansök på Arbetsförmedlingen."""
        self.driver.get(job['url'])
        time.sleep(3)

        # Leta efter ansökningslänk
        apply_selectors = [
            "a[data-testid*='apply']",
            "a[href*='apply']",
            "button[data-testid*='apply']",
        ]
        # Sök även på text
        try:
            from selenium.webdriver.common.by import By as B
            links = self.driver.find_elements(B.PARTIAL_LINK_TEXT, 'Ansök')
            if not links:
                links = self.driver.find_elements(B.PARTIAL_LINK_TEXT, 'ansök')
        except Exception:
            links = []

        apply_element = None
        for sel in apply_selectors:
            els = self.driver.find_elements(By.CSS_SELECTOR, sel)
            if els:
                apply_element = els[0]
                break
        if not apply_element and links:
            apply_element = links[0]

        if not apply_element:
            return 'skipped (ingen ansökningsknapp hittad)'

        href = apply_element.get_attribute('href') or ''
        if href and 'arbetsformedlingen.se' not in href and href.startswith('http'):
            return 'skipped (extern arbetsgivarsida)'

        apply_element.click()
        time.sleep(3)

        if 'arbetsformedlingen.se' not in self.driver.current_url:
            return 'skipped (redirectad till extern sida)'

        if dry_run:
            return 'prefilled (dry-run — skickades ej)'

        return 'skipped (AF-formulär kräver manuell hantering)'

    def generate_documents_for_job(self, job: Dict, job_number: int,
                                   ats_filter: bool = False,
                                   ats_threshold: int = 65,
                                   auto_apply: bool = False) -> bool:
        """Generera CV och personligt brev för specifikt jobb"""
        print(f"\n{'='*80}")
        print(f"📄 GENERERAR DOKUMENT #{job_number}")
        print(f"{'='*80}")
        print(f"Titel:     {job['title']}")
        print(f"Företag:   {job['company']}")
        print(f"Plats:     {job['location']}")
        print(f"Källa:     {job['source']}")
        print(f"{'='*80}")

        try:
            # Skapa jobbmapp
            safe_company = "".join(c for c in job['company'] if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_title = "".join(c for c in job['title'][:30] if c.isalnum() or c in (' ', '-', '_')).strip()
            job_folder = self.base_output_dir / f"Job_{job_number:03d}_{safe_company}_{safe_title}"
            job_folder.mkdir(exist_ok=True)

            # Hämta jobbinformation
            print(f"\n🔗 Hämtar jobbinformation från: {job['url']}")
            self.modern_facade.link_to_job(job['url'])

            # ATS-filter: kontrollera matchning INNAN vi genererar dokument
            if ats_filter:
                desc = ''
                if hasattr(self.modern_facade, 'job') and self.modern_facade.job:
                    desc = getattr(self.modern_facade.job, 'description', '') or ''
                score, reasoning = self.quick_ats_score(desc, ats_threshold)
                print(f"   🎯 ATS-poäng: {score}/100 (tröskel: {ats_threshold})")
                if score < ats_threshold:
                    short_reason = reasoning[:80] + ('...' if len(reasoning) > 80 else '')
                    print(f"   ⏭️  Hoppar över: poäng under tröskel — {short_reason}")
                    return False
                print(f"   ✅ ATS-poäng OK — fortsätter med generering")

            # Generera jobbanpassat CV (utan frågor för att spara tid)
            _design = os.getenv("CV_DESIGN", "design_01_minimal")
            print(f"📝 Genererar jobbanpassat CV ({_design})...")
            cv_base64, _ = self.modern_facade.create_resume_pdf_job_tailored(ask_questions=False)

            _cv_design_slug = os.getenv("CV_DESIGN", "design_01_minimal")
            cv_path = job_folder / f"CV_{safe_company}_{safe_title}_{_cv_design_slug}.pdf"
            with open(cv_path, 'wb') as f:
                f.write(base64.b64decode(cv_base64))

            print(f"✅ CV sparat: {cv_path.name} ({cv_path.stat().st_size / 1024:.1f} KB)")

            # Generera personligt brev
            print("💌 Genererar anpassat personligt brev...")
            cover_base64, _ = self.modern_facade.create_cover_letter()

            cover_path = job_folder / f"Personligt_Brev_{safe_company}_{safe_title}_{_cv_design_slug}.pdf"
            with open(cover_path, 'wb') as f:
                f.write(base64.b64decode(cover_base64))

            print(f"✅ Personligt brev sparat: {cover_path.name} ({cover_path.stat().st_size / 1024:.1f} KB)")

            # Spara jobbeskrivning för ATS-analys
            if hasattr(self.modern_facade, 'job') and self.modern_facade.job:
                desc = getattr(self.modern_facade.job, 'description', '') or ''
                if desc:
                    (job_folder / 'job_description.txt').write_text(desc, encoding='utf-8')

            # Spara jobbinfo
            job_info_path = job_folder / "job_info.txt"
            with open(job_info_path, 'w', encoding='utf-8') as f:
                f.write("="*80 + "\n")
                f.write("JOBBINFORMATION\n")
                f.write("="*80 + "\n\n")
                f.write(f"Titel: {job['title']}\n")
                f.write(f"Företag: {job['company']}\n")
                f.write(f"Plats: {job['location']}\n")
                f.write(f"Källa: {job['source']}\n")
                f.write(f"Hittad: {job['found_date']}\n\n")

                f.write("="*80 + "\n")
                f.write("HUR MAN SÖKER\n")
                f.write("="*80 + "\n\n")
                f.write(f"{job['source']} URL: {job['url']}\n\n")
                f.write("INSTRUKTIONER:\n")
                f.write("1. Gå till URL ovan\n")
                f.write("2. Klicka på 'Ansök' eller 'Easy Apply'\n")
                f.write("3. Bifoga CV och personligt brev från denna mapp\n")
                f.write("4. Fyll i eventuella frågor från arbetsgivaren\n\n")

            print(f"\n📁 Alla filer sparade i: {job_folder}")

            # Auto-apply om aktiverat
            if auto_apply:
                print("🚀 Auto-ansöker...")
                apply_result = self.attempt_auto_apply(job, job_folder)
                print(f"   Auto-ansök: {apply_result}")
                # Spara status i job_info.txt
                with open(job_folder / "job_info.txt", 'a', encoding='utf-8') as f:
                    f.write(f"\nAuto-ansök status: {apply_result}\n")

            # Markera som processad
            self.save_processed_job(job)

            return True

        except Exception as e:
            print(f"\n❌ Fel vid generering: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def process_jobs_interactive(self, jobs: List[Dict]):
        """Processera jobb interaktivt"""
        print(f"\n{'='*80}")
        print(f"📋 INTERAKTIV JOBBPROCESSERING ({len(jobs)} jobb)")
        print(f"{'='*80}")

        successful = 0
        for i, job in enumerate(jobs, 1):
            print(f"\n{'='*80}")
            print(f"JOBB {i}/{len(jobs)}")
            print(f"{'='*80}")
            print(f"Titel:     {job['title']}")
            print(f"Företag:   {job['company']}")
            print(f"Plats:     {job['location']}")
            print(f"Källa:     {job['source']}")
            print(f"{'='*80}")

            print("\nVad vill du göra?")
            print("  1. ✅ Generera CV och personligt brev")
            print("  2. ⏭️  Hoppa över")
            print("  3. 🛑 Avsluta")

            choice = input("\nVälj (1-3) [1]: ").strip()

            if choice == '3':
                print("\n👋 Avslutar...")
                break
            elif choice == '2':
                print("⏭️  Hoppar över...")
                continue
            else:
                success = self.generate_documents_for_job(job, i)
                if success:
                    successful += 1
                    time.sleep(2)

        return successful

    def process_jobs_automatic(self, jobs: List[Dict]):
        """Processera jobb automatiskt"""
        print(f"\n{'='*80}")
        print(f"🚀 AUTOMATISK JOBBPROCESSERING ({len(jobs)} jobb)")
        print(f"{'='*80}")

        successful = 0
        for i, job in enumerate(jobs, 1):
            print(f"\n[{i}/{len(jobs)}]")
            success = self.generate_documents_for_job(job, i)
            if success:
                successful += 1
                time.sleep(2)  # Paus mellan genereringar

        return successful

    def run(self):
        """Huvudworkflow"""
        try:
            # Initialisera system
            self.initialize()

            # Visa meny och få användarens val
            settings = self.show_main_menu()

            # Sök jobb
            print(f"\n{'='*80}")
            print("🔍 STARTAR JOBBSÖKNING")
            print(f"{'='*80}")
            print(f"Plattformar: {', '.join(settings['platforms'])}")
            print(f"Max jobb: {settings['max_jobs']}")
            print(f"Läge: {'Automatisk' if settings['auto_generate'] else 'Interaktiv'}")
            print(f"{'='*80}")

            jobs = self.search_jobs(settings['platforms'], settings['max_jobs'])

            if not jobs:
                print("\n❌ Inga jobb hittades!")
                return

            # Sammanfattning
            print(f"\n{'='*80}")
            print(f"📊 SAMMANFATTNING AV SÖKNING")
            print(f"{'='*80}")
            linkedin_count = sum(1 for j in jobs if j['source'] == 'LinkedIn')
            indeed_count = sum(1 for j in jobs if j['source'] == 'Indeed')
            af_count = sum(1 for j in jobs if j['source'] == 'Arbetsförmedlingen')
            print(f"LinkedIn:           {linkedin_count} jobb")
            print(f"Indeed:             {indeed_count} jobb")
            print(f"Arbetsförmedlingen: {af_count} jobb")
            print(f"TOTALT:             {len(jobs)} jobb")
            print(f"{'='*80}")

            # Processera jobb
            if settings['auto_generate']:
                successful = self.process_jobs_automatic(jobs)
            else:
                successful = self.process_jobs_interactive(jobs)

            # Slutsammanfattning
            print(f"\n{'='*80}")
            print(f"✅ KLART!")
            print(f"{'='*80}")
            print(f"Processade: {successful}/{len(jobs)} jobb")
            print(f"📁 Dokument: {self.base_output_dir.absolute()}")
            print(f"{'='*80}")

        except KeyboardInterrupt:
            print("\n\n⚠️  Avbrutet av användare")
        except Exception as e:
            print(f"\n❌ Fel: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            self.cleanup()

    def cleanup(self):
        """Stäng browser"""
        print("\n🧹 Stänger browser...")
        if BROWSER_POOL_AVAILABLE:
            cleanup_browser()
        elif self.driver:
            self.driver.quit()
        print("✅ Systemet stängt")


def main():
    """Main entry point"""
    print("\n" + "="*80)
    print("🎯 JOB MASTER")
    print("Ultimat Jobbsöknings- och Ansökningssystem")
    print("="*80)
    print("Skapad av: Victor Vilches")
    print("Version: 1.0 MASTER")
    print("="*80)

    job_master = JobMaster()
    job_master.run()

    print("\n👋 Tack för att du använde Job Master!")
    print(f"📁 Alla filer finns i: {job_master.base_output_dir.absolute()}")


if __name__ == "__main__":
    main()
