"""
Regenererar CV och personligt brev for Job_008.
Kor: python regenerate_job008.py
"""
import sys, os, base64
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

from dotenv import load_dotenv
load_dotenv()

JOB_FOLDER = PROJECT_DIR / 'data_folder' / 'output' / 'job_master' / 'Job_004_Academic Work Sweden AB_Fullstack-utvecklare till Rado'
DESIGN  = 'design_02_classic'
COMPANY = 'Academic Work Sweden AB'
TITLE   = 'Fullstack-utvecklare till Rado'


def read_env():
    env = {}
    f = PROJECT_DIR / '.env'
    if f.exists():
        for line in f.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main():
    print("=" * 60)
    env = read_env()
    provider = env.get('LLM_PROVIDER', 'openai')

    # Plocka forsta tillgangliga nyckel dynamiskt
    api_key = next((v for k, v in env.items() if k.endswith('_API_KEY') and v), '')
    print(f"Provider: {provider}  |  Nyckel: {'OK' if api_key else 'SAKNAS'}")
    if not api_key:
        sys.exit("FEL: Ingen API-nyckel i .env")

    desc_file = JOB_FOLDER / 'job_description.txt'
    job_description = desc_file.read_text(encoding='utf-8')
    print(f"Jobbeskrivning: {len(job_description)} tecken")

    from src.resume_schemas.resume import Resume
    yaml_path = PROJECT_DIR / 'data_folder' / 'plain_text_resume.yaml'
    resume_object = Resume(yaml_path.read_text(encoding='utf-8'))
    print("Resume YAML laddad")

    from src.job import Job
    job = Job()
    job.description = job_description
    job.role        = TITLE
    job.company     = COMPANY
    job.location    = 'Stockholm'
    job.link        = 'Job_008'

    print("Startar Chrome...")
    try:
        from src.utils.browser_pool import get_browser
        driver = get_browser()
    except Exception:
        from src.utils.chrome_utils import init_browser
        driver = init_browser()
    print("Chrome OK")

    from src.libs.resume_and_cover_builder.moderndesign1.modern_facade import ModernDesign1Facade
    from src.libs.resume_and_cover_builder.moderndesign1.modern_style_manager import ModernDesign1StyleManager
    from src.libs.resume_and_cover_builder.moderndesign1.modern_resume_generator import ModernDesign1ResumeGenerator

    style_manager = ModernDesign1StyleManager()
    style_manager.set_selected_style('Modern Design 1 - Default')
    resume_gen = ModernDesign1ResumeGenerator()

    facade = ModernDesign1Facade(
        api_key=api_key,
        style_manager=style_manager,
        resume_generator=resume_gen,
        resume_object=resume_object,
        output_path=JOB_FOLDER,
    )
    facade.set_driver(driver)
    facade.job = job

    print("Genererar CV (AI + PDF)... ~30 sek")
    cv_b64, _ = facade.create_resume_pdf_job_tailored()
    for old in JOB_FOLDER.glob('CV_*.pdf'):
        old.unlink()
    cv_path = JOB_FOLDER / f'CV_{COMPANY}_{TITLE}_{DESIGN}.pdf'
    cv_path.write_bytes(base64.b64decode(cv_b64))
    print(f"CV sparat: {cv_path.name}  ({cv_path.stat().st_size/1024:.1f} KB)")

    print("Genererar personligt brev...")
    cover_b64, _ = facade.create_cover_letter()
    for old in JOB_FOLDER.glob('Personligt_Brev_*.pdf'):
        old.unlink()
    cover_path = JOB_FOLDER / f'Personligt_Brev_{COMPANY}_{TITLE}_{DESIGN}.pdf'
    cover_path.write_bytes(base64.b64decode(cover_b64))
    print(f"Brev sparat: {cover_path.name}  ({cover_path.stat().st_size/1024:.1f} KB)")

    print("=" * 60)
    print("KLAR! Oppna ApplyMind AI och ladda ner det nya CV:t.")


if __name__ == '__main__':
    main()
