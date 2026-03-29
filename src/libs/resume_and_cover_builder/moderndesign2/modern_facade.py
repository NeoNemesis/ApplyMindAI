"""
ModernDesign2Facade - Följer EXAKT samma pattern som ModernDesign1Facade
Men använder Modern Design 2 specifika komponenter (kreativ sidopanel-design)
"""

import hashlib
from pathlib import Path
from typing import Tuple
from loguru import logger

from src.job import Job
from src.utils.chrome_utils import HTML_to_PDF
from src.libs.resume_and_cover_builder.llm.llm_job_parser import LLMParser
from src.libs.resume_and_cover_builder.config import global_config

class ModernDesign2Facade:
    """
    Modern Design 2 Facade - SAMMA INTERFACE SOM ModernDesign1Facade
    Men använder Modern Design 2 kreativa komponenter internt
    """
    
    def __init__(self, api_key: str, style_manager, resume_generator, resume_object, output_path: Path):
        """
        Initialize ModernDesign2Facade - EXAKT SAMMA SIGNATURE
        
        Args:
            api_key (str): The OpenAI API key
            style_manager: The StyleManager instance
            resume_generator: The ResumeGenerator instance
            resume_object: The resume object
            output_path (Path): The output path
        """
        # EXAKT SAMMA global_config INITIERING
        lib_directory = Path(__file__).resolve().parent.parent
        global_config.STRINGS_MODULE_RESUME_PATH = lib_directory / "resume_prompt/strings_applymind.py"
        global_config.STRINGS_MODULE_RESUME_JOB_DESCRIPTION_PATH = lib_directory / "resume_job_description_prompt/strings_applymind.py"
        global_config.STRINGS_MODULE_COVER_LETTER_JOB_DESCRIPTION_PATH = lib_directory / "cover_letter_prompt/strings_applymind.py"
        global_config.STRINGS_MODULE_NAME = "strings_applymind"
        global_config.STYLES_DIRECTORY = lib_directory / "resume_style"
        global_config.LOG_OUTPUT_FILE_PATH = output_path
        global_config.API_KEY = api_key
        
        self.api_key = api_key
        self.style_manager = style_manager
        self.resume_generator = resume_generator
        self.resume_generator.set_resume_object(resume_object)
        self.output_path = output_path
        self.driver = None
        self.job = None
        
        logger.info("🎨 ModernDesign2Facade initialiserad med kreativ sidopanel-design")
    
    def set_driver(self, driver):
        """Sätt WebDriver - SAMMA SOM ModernDesign1Facade"""
        self.driver = driver
        logger.debug("🌐 WebDriver satt för ModernDesign2Facade")
    
    def link_to_job(self, job_url: str):
        """Länka till jobb - SAMMA SOM ModernDesign1Facade"""
        try:
            logger.info(f"🔗 Modern Design 2: Länkar till jobb: {job_url}")
            
            self.driver.set_page_load_timeout(30)
            self.driver.get(job_url)
            self.driver.implicitly_wait(10)
            
            body_element = self.driver.find_element("tag name", "body")
            body_element = body_element.get_attribute("outerHTML")
            
            self.llm_job_parser = LLMParser(openai_api_key=global_config.API_KEY)
            self.llm_job_parser.set_body_html(body_element)

            self.job = Job()
            
            try:
                self.job.role = self.llm_job_parser.extract_role()
            except Exception as e:
                logger.warning(f"⚠️ Kunde inte extrahera roll: {e}")
                self.job.role = "Creative Professional"
            
            try:
                self.job.company = self.llm_job_parser.extract_company_name()
            except Exception as e:
                logger.warning(f"⚠️ Kunde inte extrahera företag: {e}")
                self.job.company = "Company"
            
            try:
                self.job.description = self.llm_job_parser.extract_job_description()
            except Exception as e:
                logger.warning(f"⚠️ Kunde inte extrahera beskrivning: {e}")
                self.job.description = "Creative professional role"
            
            try:
                self.job.location = self.llm_job_parser.extract_location()
            except Exception as e:
                logger.warning(f"⚠️ Kunde inte extrahera plats: {e}")
                self.job.location = "Stockholm"
            
            self.job.link = job_url
            logger.info(f"✅ Modern Design 2: Jobb extraherat från URL: {job_url}")
            
        except Exception as e:
            logger.error(f"❌ Modern Design 2: Fel vid jobb-länkning: {e}")
            self.job = Job()
            self.job.role = "Creative Professional"
            self.job.company = "Company"
            self.job.description = "Creative professional role"
            self.job.location = "Stockholm"
            self.job.link = job_url
            logger.info(f"🔄 Modern Design 2: Använder fallback job-objekt")
    
    def create_resume_pdf_job_tailored(self) -> Tuple[str, str]:
        """
        Skapa jobbanpassat CV - EXAKT SAMMA LOGIK SOM ModernDesign1Facade
        
        Returns:
            Tuple[str, str]: (base64_pdf, suggested_name)
        """
        style_path = self.style_manager.get_style_path()
        if style_path is None:
            raise ValueError("You must choose a style before generating the PDF.")

        html_resume = self._create_modern_design2_resume(style_path, self.job.description)

        suggested_name = hashlib.md5(self.job.link.encode()).hexdigest()[:10]
        
        try:
            logger.info("📄 Modern Design 2: Genererar PDF...")
            result = HTML_to_PDF(html_resume, self.driver)
            logger.info("✅ Modern Design 2: PDF genererad")
        except Exception as e:
            logger.error(f"❌ Modern Design 2: Fel vid PDF-generering: {e}")
            raise
        # ✅ PERFORMANCE FIX: Don't quit driver! Browser pool manages lifecycle
        
        return result, suggested_name
    
    def _create_modern_design2_resume(self, style_path: Path, job_description: str) -> str:
        """
        Skapa Modern Design 2 CV med kreativ sidopanel-design
        
        Args:
            style_path: Sökväg till CSS-fil
            job_description: Jobbeskrivning
            
        Returns:
            str: Komplett HTML för CV:et (med CSS och struktur)
        """
        logger.info("🎯 Skapar Modern Design 2 CV med kreativ sidopanel-design")
        
        from .improved_generator import ImprovedModernDesign2Generator
        
        generator = ImprovedModernDesign2Generator(
            self.resume_generator.resume_object, 
            global_config.API_KEY
        )
        
        complete_html = generator.generate_complete_cv_html(job_description)
        
        logger.info(f"✅ Modern Design 2 CV genererat: {len(complete_html)} tecken")
        return complete_html
    
    def create_cover_letter(self) -> Tuple[str, str]:
        """
        Skapa personligt brev - SAMMA INTERFACE SOM ModernDesign1Facade
        
        Returns:
            Tuple[str, str]: (base64_pdf, suggested_name)
        """
        if not self.job:
            raise ValueError("Jobb måste länkas innan cover letter kan genereras")
        
        logger.info("📧 Modern Design 2: Skapar personligt brev med gradient-design")
        
        from .cover_letter_generator import ModernDesign2CoverLetterGenerator
        
        generator = ModernDesign2CoverLetterGenerator(
            self.resume_generator.resume_object,
            self.api_key
        )
        
        # Generera HTML
        cover_letter_html = generator.generate_cover_letter_html(
            job_description=self.job.description,
            company_name=self.job.company,
            position_title=self.job.role,
            company_address=""
        )
        
        # Generera PDF
        suggested_name = hashlib.md5(self.job.link.encode()).hexdigest()[:10]
        
        try:
            logger.info("📄 Modern Design 2: Genererar Cover Letter PDF...")
            result = HTML_to_PDF(cover_letter_html, self.driver)
            logger.info("✅ Modern Design 2: Cover Letter PDF genererad")
        except Exception as e:
            logger.error(f"❌ Modern Design 2: Fel vid Cover Letter PDF-generering: {e}")
            raise
        # ✅ PERFORMANCE FIX: Don't quit driver! Browser pool manages lifecycle
        
        return result, suggested_name

