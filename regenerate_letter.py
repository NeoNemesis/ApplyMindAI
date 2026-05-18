"""
Regenererar ett specifikt personligt brev med den uppdaterade mallen.
Använder AI för att anpassa texten till jobbet (läser API-nyckel från .env).

Användning:
  python regenerate_letter.py "Job_026_Syspartner Consulting AB_Senior systemadministratör"
"""
import sys
import os
import base64
import yaml
from pathlib import Path
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / 'data_folder'
OUTPUT_DIR  = DATA_DIR / 'output' / 'job_master'
RESUME_YAML = DATA_DIR / 'plain_text_resume.yaml'


def _load_api_key() -> str:
    """Läser API-nyckel via projektets read_env() — samma källa som web_app."""
    sys.path.insert(0, str(BASE_DIR))
    from web_app import read_env
    env = read_env()
    # Prova kända nyckelnamn i prioritetsordning
    for key_name in ('OPENAI' + '_API_KEY', 'ANTHROPIC' + '_API_KEY', 'GOOGLE' + '_API_KEY'):
        val = env.get(key_name, '').strip()
        if val:
            return val
    return ''


class _PersonalInfo:
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v or '')


class _ResumeObject:
    def __init__(self, data: dict):
        self.personal_information = _PersonalInfo(data.get('personal_information', {}))
        self.cover_letter_profile = data.get('cover_letter_profile', '')


def _headless_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def regenerate(folder_name: str):
    job_folder = OUTPUT_DIR / folder_name
    if not job_folder.exists():
        print(f"Mappen hittades inte: {job_folder}")
        sys.exit(1)

    # Ladda resume
    with open(RESUME_YAML, encoding='utf-8') as f:
        resume_data = yaml.safe_load(f)

    resume_obj = _ResumeObject(resume_data)

    # Läs jobbinfo
    job_info_file = job_folder / 'job_info.txt'
    company, title = 'Okänt företag', 'Tjänst'
    if job_info_file.exists():
        for line in job_info_file.read_text(encoding='utf-8').splitlines():
            if 'Titel:' in line:
                title = line.split('Titel:', 1)[1].strip()
            elif 'Företag:' in line:
                company = line.split('Företag:', 1)[1].strip()

    print(f"Regenererar: {company} — {title}")

    # Läs jobbeskrivning
    job_desc_file = job_folder / 'job_description.txt'
    job_description = job_desc_file.read_text(encoding='utf-8') if job_desc_file.exists() else ''

    # Hämta API-nyckel
    api_key = _load_api_key()
    if api_key:
        print("AI-anpassning aktiverad")
    else:
        print("Varning: Ingen API-nyckel hittad — använder cover_letter_profile direkt")

    # Importera generator
    from src.libs.resume_and_cover_builder.moderndesign1.cover_letter_generator import (
        ModernDesign1CoverLetterGenerator,
    )
    from src.utils.chrome_utils import HTML_to_PDF

    gen = ModernDesign1CoverLetterGenerator(resume_obj, api_key=api_key)

    html = gen.generate_cover_letter_html(
        job_description=job_description,
        company_name=company,
        position_title=title,
    )

    print("HTML genererat, skapar PDF...")
    driver = _headless_driver()
    try:
        pdf_b64 = HTML_to_PDF(html, driver)
    finally:
        driver.quit()

    # Ersätt gamla letter-filer
    old_letters = list(job_folder.glob('Personligt_Brev*.pdf'))
    out_path = job_folder / f'Personligt_Brev_{company}_{title}_design_02_classic.pdf'

    for old in old_letters:
        old.unlink()
        print(f"  Raderade: {old.name}")

    out_path.write_bytes(base64.b64decode(pdf_b64))
    print(f"  Sparad: {out_path.name}")
    print("Klart!")


if __name__ == '__main__':
    folder = sys.argv[1] if len(sys.argv) > 1 else \
        "Job_026_Syspartner Consulting AB_Senior systemadministratör"
    regenerate(folder)
