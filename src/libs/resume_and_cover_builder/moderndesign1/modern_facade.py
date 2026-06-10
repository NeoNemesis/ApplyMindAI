"""
ModernDesign1Facade - Följer EXAKT samma pattern som ResumeFacade
Men använder Modern Design 1 specifika komponenter
"""

import hashlib
from pathlib import Path
from typing import Tuple
from loguru import logger

from src.job import Job
from src.utils.chrome_utils import HTML_to_PDF
from src.libs.resume_and_cover_builder.llm.llm_job_parser import LLMParser
from src.libs.resume_and_cover_builder.config import global_config
# ai_generator borttagen - använder nu smart_data_generator

class ModernDesign1Facade:
    """
    Modern Design 1 Facade - SAMMA INTERFACE SOM ResumeFacade
    Men använder Modern Design 1 komponenter internt
    """
    
    def __init__(self, api_key: str, style_manager, resume_generator, resume_object, output_path: Path,
                 data_dir: Path = None):
        """
        Initialize ModernDesign1Facade - EXAKT SAMMA SIGNATURE SOM ResumeFacade

        Args:
            api_key (str): The OpenAI API key
            style_manager: The StyleManager instance
            resume_generator: The ResumeGenerator instance
            resume_object: The resume object
            output_path (Path): The output path
            data_dir (Path): Per-user datakatalog (foton, referensbrev).
                             None = desktop-läge med delad data_folder.
        """
        # EXAKT SAMMA global_config INITIERING SOM ResumeFacade
        lib_directory = Path(__file__).resolve().parent.parent
        global_config.STRINGS_MODULE_RESUME_PATH = lib_directory / "resume_prompt/strings_applymind.py"
        global_config.STRINGS_MODULE_RESUME_JOB_DESCRIPTION_PATH = lib_directory / "resume_job_description_prompt/strings_applymind.py"
        global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH = lib_directory / "cover_letter_prompt/strings_applymind.py"
        global_config.STRINGS_MODULE_NAME = "strings_applymind"
        global_config.STYLES_DIRECTORY = lib_directory / "resume_style"
        global_config.LOG_OUTPUT_FILE_PATH = output_path
        global_config.API_KEY = api_key

        self.api_key = api_key
        self.data_dir = Path(data_dir) if data_dir else None
        self.style_manager = style_manager
        self.resume_generator = resume_generator
        self.resume_generator.set_resume_object(resume_object)  # SAMMA SOM ResumeFacade
        self.output_path = output_path
        self.driver = None
        self.job = None  # SAMMA SOM ResumeFacade - Job objekt, inte bara URL

        logger.info("🎨 ModernDesign1Facade initialiserad med EXAKT samma global_config som ResumeFacade")
    
    def set_driver(self, driver):
        """Sätt WebDriver - SAMMA SOM ResumeFacade"""
        self.driver = driver
        logger.debug("🌐 WebDriver satt för ModernDesign1Facade")
    
    def _fetch_html_via_requests(self, job_url: str) -> str:
        """Hämta sida via requests när browser saknas. Returnerar body-HTML eller tom sträng."""
        try:
            import requests as _req
            from bs4 import BeautifulSoup as _BS
            resp = _req.get(job_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36',
                'Accept-Language': 'sv-SE,sv;q=0.9,en;q=0.8',
            }, timeout=15, allow_redirects=True)
            soup = _BS(resp.text, 'html.parser')
            body = soup.find('body')
            return str(body) if body else resp.text
        except Exception as e:
            logger.warning(f"⚠️ requests-fallback misslyckades för {job_url}: {e}")
            return ''

    def link_to_job(self, job_url: str, job_title: str = "", job_company: str = ""):
        """Länka till jobb - FÖRBÄTTRAD VERSION MED TIMEOUT-HANTERING"""
        self._job_title_hint = job_title
        self._job_company_hint = job_company
        try:
            logger.info(f"🔗 Modern Design 1: Länkar till jobb: {job_url}")

            # Hämta HTML — browser om tillgänglig, annars requests-fallback
            if self.driver is not None:
                self.driver.set_page_load_timeout(30)
                self.driver.get(job_url)
                self.driver.implicitly_wait(10)
                body_element_obj = self.driver.find_element("tag name", "body")
                body_element = body_element_obj.get_attribute("outerHTML")
            else:
                logger.info("🔄 Browser ej tillgänglig — använder requests-fallback")
                body_element = self._fetch_html_via_requests(job_url)

            # Extrahera ren text från HTML för språkdetektering
            # Detta ger oss HELA jobbeskrivningen, inte bara sammanfattningen
            import re
            from html import unescape

            # Ta bort script och style tags
            body_text = re.sub(r'<script[^>]*>.*?</script>', '', body_element, flags=re.DOTALL | re.IGNORECASE)
            body_text = re.sub(r'<style[^>]*>.*?</style>', '', body_text, flags=re.DOTALL | re.IGNORECASE)
            # Ta bort HTML tags
            body_text = re.sub(r'<[^>]+>', ' ', body_text)
            # Avkoda HTML entities
            body_text = unescape(body_text)
            # Ta bort extra whitespace
            body_text = re.sub(r'\s+', ' ', body_text).strip()

            # Spara den fulla texten för språkdetektering
            self.full_job_text = body_text
            logger.debug(f"📄 Full jobbtext extraherad: {len(body_text)} tecken")
            logger.debug(f"📝 Första 200 tecken: {body_text[:200]}")

            # Skapa LLMParser med timeout
            self.llm_job_parser = LLMParser(openai_api_key=global_config.API_KEY)
            self.llm_job_parser.set_body_html(body_element)

            self.job = Job()

            # Extrahera jobbinformation med timeout-hantering
            try:
                self.job.role = self.llm_job_parser.extract_role()
            except Exception as e:
                logger.warning(f"⚠️ Kunde inte extrahera roll: {e}")
                self.job.role = "Dataingenjör"

            try:
                self.job.company = self.llm_job_parser.extract_company_name()
            except Exception as e:
                logger.warning(f"⚠️ Kunde inte extrahera företag: {e}")
                self.job.company = "Företag"

            try:
                extracted = self.llm_job_parser.extract_job_description()
                # Detect LLM failure responses (GPT says "I'm sorry..." when context is empty)
                _error_patterns = ["i'm sorry", "i cannot", "cannot provide", "not included in", "no job description"]
                # Detect bot/captcha pages (short text with no Swedish content)
                _is_bot_page = body_text and len(body_text) < 1000 and sum(1 for c in body_text if c in 'åäöÅÄÖ') == 0
                if extracted and not any(p in extracted.lower() for p in _error_patterns):
                    self.job.description = extracted
                elif _is_bot_page and self._job_title_hint:
                    # Bot detection page AND we have job title hint — use title as description context
                    logger.warning(f"⚠️ Bot-skyddssida detekterad ({len(body_text)} tecken, inga svenska tecken) - använder jobbtitelledtråd")
                    self.job.description = f"Tjänst: {self._job_title_hint}\nFöretag: {self._job_company_hint}\n\nVi söker en engagerad {self._job_title_hint} till vårt team. Tjänsten kräver teknisk kompetens och erfarenhet av webbutveckling."
                else:
                    # Fall back to raw page text — already in Swedish if job is Swedish
                    logger.warning("⚠️ LLM-extraktion misslyckades, använder rå sidtext som beskrivning")
                    self.job.description = body_text[:4000] if body_text else "Vi söker en engagerad medarbetare."
            except Exception as e:
                logger.warning(f"⚠️ Kunde inte extrahera beskrivning: {e}")
                self.job.description = body_text[:4000] if body_text else "Vi söker en engagerad medarbetare."

            try:
                self.job.location = self.llm_job_parser.extract_location()
            except Exception as e:
                logger.warning(f"⚠️ Kunde inte extrahera plats: {e}")
                self.job.location = "Stockholm"

            self.job.link = job_url
            logger.info(f"✅ Modern Design 1: Jobb extraherat från URL: {job_url}")

        except Exception as e:
            logger.error(f"❌ Modern Design 1: Fel vid jobb-länkning: {e}")
            # Skapa fallback job-objekt, bevara body_text om den hann extraheras
            _fallback_raw = getattr(self, 'full_job_text', '') or ""
            _title_hint = getattr(self, '_job_title_hint', '')
            _company_hint = getattr(self, '_job_company_hint', '')
            if _title_hint:
                _fallback_text = f"Tjänst: {_title_hint}\nFöretag: {_company_hint}\n\nVi söker en engagerad {_title_hint} till vårt team."
            else:
                _fallback_text = _fallback_raw or "Vi söker en engagerad medarbetare med IT-kompetens."
            self.job = Job()
            self.job.role = _title_hint or "Systemutvecklare"
            self.job.company = _company_hint or "Företag"
            self.job.description = _fallback_text[:4000]
            self.job.location = "Sverige"
            self.job.link = job_url
            self.full_job_text = _fallback_text
            logger.info(f"🔄 Modern Design 1: Använder fallback job-objekt")

    def create_resume_pdf_job_tailored(self) -> Tuple[str, str]:
        """
        Skapa jobbanpassat CV - AI anpassar automatiskt utifrån jobbeskrivningen.

        Returns:
            Tuple[str, str]: (base64_pdf, suggested_name)
        """
        # EXAKT SAMMA LOGIK SOM ResumeFacade.create_resume_pdf_job_tailored()
        style_path = self.style_manager.get_style_path()  # SAMMA METOD-NAMN SOM ResumeFacade
        if style_path is None:
            raise ValueError("You must choose a style before generating the PDF.")

        # ANVÄND resume_generator EXAKT som ResumeFacade
        # Men istället för create_resume_job_description_text, använd Modern Design 1 generator
        html_resume = self._create_modern_design1_resume(style_path, self.job.description)

        # Generate a unique name using the job URL hash - EXAKT SOM ResumeFacade
        suggested_name = hashlib.md5(self.job.link.encode()).hexdigest()[:10]
        
        # Generera PDF med timeout-hantering
        try:
            logger.info("📄 Modern Design 1: Genererar PDF...")
            result = HTML_to_PDF(html_resume, self.driver)
            logger.info("✅ Modern Design 1: PDF genererad")
        except Exception as e:
            logger.error(f"❌ Modern Design 1: Fel vid PDF-generering: {e}")
            raise
        # ✅ PERFORMANCE FIX: Don't quit driver! Browser pool manages lifecycle
        # finally block removed - no driver.quit() needed
        
        return result, suggested_name
    
    def _create_modern_design1_resume(self, style_path: Path, job_description: str) -> str:
        """
        Skapa Modern Design 1 CV - AI anpassar upp till 25% av texten mot jobbeskrivningen.

        Args:
            style_path: Sökväg till CSS-fil
            job_description: Jobbeskrivning (sammanfattad från LLM)

        Returns:
            str: Komplett HTML för CV:et (med CSS och struktur)
        """
        logger.info("🎯 Skapar jobbanpassat CV (AI anpassar upp till 25% av texten)")

        # Använd förbättrad generator som matchar exakt design från bilden
        from .improved_generator import ImprovedModernDesign1Generator

        # Skapa generator som använder förbättrad template
        generator = ImprovedModernDesign1Generator(
            self.resume_generator.resume_object,
            global_config.API_KEY,
            data_dir=self.data_dir
        )

        # Använd FULL jobbtext för språkdetektering om tillgänglig
        # Men använd sammanfattad beskrivning för CV-innehåll
        text_for_language_detection = getattr(self, 'full_job_text', job_description)

        logger.info(f"🌍 Använder {len(text_for_language_detection)} tecken för språkdetektering")
        logger.debug(f"📝 Språkdetekteringstext (första 200 tecken): {text_for_language_detection[:200]}")

        # Generera komplett HTML med förbättrad struktur
        # Skicka både full text (för språk) och sammanfattning (för innehåll)
        complete_html = generator.generate_complete_cv_html(
            job_description=job_description,
            job_description_for_language=text_for_language_detection
        )

        logger.info(f"✅ Modern Design 1 CV genererat: {len(complete_html)} tecken")
        return complete_html
    
    def create_cover_letter(self) -> Tuple[str, str]:
        """
        Skapa personligt brev - SAMMA INTERFACE SOM ResumeFacade
        
        Returns:
            Tuple[str, str]: (base64_pdf, suggested_name)
        """
        if not self.job:
            raise ValueError("Jobb måste länkas innan cover letter kan genereras")
        
        logger.info("📧 Modern Design 1: Skapar personligt brev")
        
        from .cover_letter_generator import ModernDesign1CoverLetterGenerator

        generator = ModernDesign1CoverLetterGenerator(
            self.resume_generator.resume_object,
            self.api_key,
            data_dir=self.data_dir
        )

        # Använd FULL jobbtext för språkdetektering om tillgänglig
        text_for_language_detection = getattr(self, 'full_job_text', self.job.description)

        logger.info(f"🌍 Cover Letter: Använder {len(text_for_language_detection)} tecken för språkdetektering")

        # Generera HTML
        cover_letter_html = generator.generate_cover_letter_html(
            job_description=self.job.description,
            job_description_for_language=text_for_language_detection,
            company_name=self.job.company,
            position_title=self.job.role,
            company_address=""
        )
        
        # Generera PDF
        suggested_name = hashlib.md5(self.job.link.encode()).hexdigest()[:10]
        
        try:
            logger.info("📄 Modern Design 1: Genererar Cover Letter PDF...")
            result = HTML_to_PDF(cover_letter_html, self.driver)
            logger.info("✅ Modern Design 1: Cover Letter PDF genererad")
        except Exception as e:
            logger.error(f"❌ Modern Design 1: Fel vid Cover Letter PDF-generering: {e}")
            raise
        # ✅ PERFORMANCE FIX: Don't quit driver! Browser pool manages lifecycle
        # finally block removed - no driver.quit() needed

        return result, suggested_name