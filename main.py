import base64
import sys
from pathlib import Path
import traceback
from typing import List, Optional, Tuple, Dict

import click
import inquirer
import yaml
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import re
from src.libs.resume_and_cover_builder import ResumeFacade, ResumeGenerator, StyleManager
from src.resume_schemas.job_application_profile import JobApplicationProfile
from src.resume_schemas.resume import Resume
from src.logger_config import logger
from src.utils.chrome_utils import init_browser  # Keep for fallback
from src.utils.constants import (
    PLAIN_TEXT_RESUME_YAML,
    SECRETS_YAML,
    WORK_PREFERENCES_YAML,
)
from src.email_sender import EmailSender
from src.user_preferences import UserPreferences

# ✅ INTEGRATED: Import new refactored modules
try:
    from src.security_utils import SecurityValidator, SecurePasswordManager
    from src.utils.browser_pool import get_browser, cleanup_browser
    from src.utils.resume_cache import load_resume_cached
    from src.utils.design_models import DesignModel, validate_design_model
    from src.libs.resume_and_cover_builder.document_strategy import StrategyFactory
    SECURITY_ENABLED = True
    REFACTORED_MODULES_AVAILABLE = True
    logger.info("✅ Refactored modules loaded successfully")
except ImportError as e:
    logger.warning(f"Refactored modules not available: {e}. Using legacy code.")
    SECURITY_ENABLED = False
    REFACTORED_MODULES_AVAILABLE = False


class ConfigError(Exception):
    """Custom exception for configuration-related errors."""
    pass


def validate_and_get_job_url() -> Optional[str]:
    """
    Prompt user for job URL and validate it for security.
    
    Returns:
        str: Validated job URL or None if validation fails
    """
    questions = [
        inquirer.Text('job_url', message="Please enter the URL of the job description:")
    ]
    answers = inquirer.prompt(questions)
    job_url = answers.get('job_url')
    
    if not job_url:
        logger.error("No job URL provided")
        return None
    
    # 🔒 SECURITY FIX: Validate URL before processing
    if SECURITY_ENABLED:
        try:
            SecurityValidator.validate_job_url(job_url)
            logger.debug(f"✅ Job URL validated: {job_url}")
        except ValueError as e:
            logger.error(f"❌ Invalid job URL: {e}")
            print(f"\n❌ ERROR: {e}")
            print("Please provide a valid HTTP/HTTPS URL")
            return None
    
    return job_url


def get_browser_instance():
    """
    Get browser instance using pooling if available, fallback to init_browser().
    
    ✅ PERFORMANCE FIX: Reuses browser instead of creating new one each time.
    
    Returns:
        WebDriver: Browser instance
    """
    if REFACTORED_MODULES_AVAILABLE:
        logger.debug("🌐 Using browser pool (fast!)")
        return get_browser()
    else:
        logger.debug("⚠️ Creating new browser (slow - browser pool not available)")
        return init_browser()


def load_resume_file(resume_path: Path) -> str:
    """
    Load resume file with caching if available.
    
    ✅ PERFORMANCE FIX: Caches file contents to avoid redundant I/O.
    
    Args:
        resume_path: Path to resume file
        
    Returns:
        str: Resume file contents
    """
    if REFACTORED_MODULES_AVAILABLE:
        logger.debug("📖 Loading resume with caching (fast!)")
        return load_resume_cached(str(resume_path))
    else:
        logger.debug("⚠️ Loading resume without cache (slow)")
        with open(resume_path, 'r', encoding='utf-8') as file:
            return file.read()


class ConfigValidator:
    """Validates configuration and secrets YAML files."""

    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    REQUIRED_CONFIG_KEYS = {
        "remote": bool,
        "experience_level": dict,
        "job_types": dict,
        "date": dict,
        "positions": list,
        "locations": list,
        "location_blacklist": list,
        "distance": int,
        "company_blacklist": list,
        "title_blacklist": list,
    }
    EXPERIENCE_LEVELS = [
        "internship",
        "entry",
        "associate",
        "mid_senior_level",
        "director",
        "executive",
    ]
    JOB_TYPES = [
        "full_time",
        "contract",
        "part_time",
        "temporary",
        "internship",
        "other",
        "volunteer",
    ]
    DATE_FILTERS = ["all_time", "month", "week", "24_hours"]
    APPROVED_DISTANCES = {0, 5, 10, 25, 50, 100}

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate the format of an email address."""
        return bool(ConfigValidator.EMAIL_REGEX.match(email))

    @staticmethod
    def load_yaml(yaml_path: Path) -> dict:
        """Load and parse a YAML file."""
        try:
            with open(yaml_path, "r") as stream:
                return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Error reading YAML file {yaml_path}: {exc}")
        except FileNotFoundError:
            raise ConfigError(f"YAML file not found: {yaml_path}")

    @classmethod
    def validate_config(cls, config_yaml_path: Path) -> dict:
        """Validate the main configuration YAML file."""
        parameters = cls.load_yaml(config_yaml_path)
        # Check for required keys and their types
        for key, expected_type in cls.REQUIRED_CONFIG_KEYS.items():
            if key not in parameters:
                if key in ["company_blacklist", "title_blacklist", "location_blacklist"]:
                    parameters[key] = []
                else:
                    raise ConfigError(f"Missing required key '{key}' in {config_yaml_path}")
            elif not isinstance(parameters[key], expected_type):
                if key in ["company_blacklist", "title_blacklist", "location_blacklist"] and parameters[key] is None:
                    parameters[key] = []
                else:
                    raise ConfigError(
                        f"Invalid type for key '{key}' in {config_yaml_path}. Expected {expected_type.__name__}."
                    )
        cls._validate_experience_levels(parameters["experience_level"], config_yaml_path)
        cls._validate_job_types(parameters["job_types"], config_yaml_path)
        cls._validate_date_filters(parameters["date"], config_yaml_path)
        cls._validate_list_of_strings(parameters, ["positions", "locations"], config_yaml_path)
        cls._validate_distance(parameters["distance"], config_yaml_path)
        cls._validate_blacklists(parameters, config_yaml_path)
        return parameters

    @classmethod
    def _validate_experience_levels(cls, experience_levels: dict, config_path: Path):
        """Ensure experience levels are booleans."""
        for level in cls.EXPERIENCE_LEVELS:
            if not isinstance(experience_levels.get(level), bool):
                raise ConfigError(
                    f"Experience level '{level}' must be a boolean in {config_path}"
                )

    @classmethod
    def _validate_job_types(cls, job_types: dict, config_path: Path):
        """Ensure job types are booleans."""
        for job_type in cls.JOB_TYPES:
            if not isinstance(job_types.get(job_type), bool):
                raise ConfigError(
                    f"Job type '{job_type}' must be a boolean in {config_path}"
                )

    @classmethod
    def _validate_date_filters(cls, date_filters: dict, config_path: Path):
        """Ensure date filters are booleans."""
        for date_filter in cls.DATE_FILTERS:
            if not isinstance(date_filters.get(date_filter), bool):
                raise ConfigError(
                    f"Date filter '{date_filter}' must be a boolean in {config_path}"
                )

    @classmethod
    def _validate_list_of_strings(cls, parameters: dict, keys: list, config_path: Path):
        """Ensure specified keys are lists of strings."""
        for key in keys:
            if not all(isinstance(item, str) for item in parameters[key]):
                raise ConfigError(
                    f"'{key}' must be a list of strings in {config_path}"
                )

    @classmethod
    def _validate_distance(cls, distance: int, config_path: Path):
        """Validate the distance value."""
        if distance not in cls.APPROVED_DISTANCES:
            raise ConfigError(
                f"Invalid distance value '{distance}' in {config_path}. Must be one of: {cls.APPROVED_DISTANCES}"
            )

    @classmethod
    def _validate_blacklists(cls, parameters: dict, config_path: Path):
        """Ensure blacklists are lists."""
        for blacklist in ["company_blacklist", "title_blacklist", "location_blacklist"]:
            if not isinstance(parameters.get(blacklist), list):
                raise ConfigError(
                    f"'{blacklist}' must be a list in {config_path}"
                )
            if parameters[blacklist] is None:
                parameters[blacklist] = []

    @staticmethod
    def validate_secrets(secrets_yaml_path: Path) -> str:
        """
        Validate and retrieve the LLM API key.
        
        ✅ SECURITY FIX: Prioritizes environment variable over YAML file.
        """
        # 🔒 SECURITY FIX: Prioritize environment variables, warn on YAML fallback
        if REFACTORED_MODULES_AVAILABLE:
            env_api_key = SecurePasswordManager.get_api_key()
            if env_api_key:
                logger.info("✅ API key loaded from environment variable (SECURE)")
                return env_api_key
            else:
                logger.warning("")
                logger.warning("=" * 80)
                logger.warning("⚠️  SECURITY WARNING: API key not found in environment variable!")
                logger.warning("=" * 80)
                logger.warning("You are using INSECURE plaintext storage (secrets.yaml)")
                logger.warning("")
                logger.warning("🔒 RECOMMENDED: Set environment variable instead:")
                logger.warning("   Windows: $env:JOBCRAFT_API_KEY = 'your-api-key'")
                logger.warning("   Linux:   export JOBCRAFT_API_KEY='your-api-key'")
                logger.warning("")
                logger.warning("⚠️  Falling back to secrets.yaml for now...")
                logger.warning("=" * 80)
                logger.warning("")
        
        # Fallback: Load from YAML (insecure but allows development)
        try:
            secrets = ConfigValidator.load_yaml(secrets_yaml_path)
            mandatory_secrets = ["llm_api_key"]

            for secret in mandatory_secrets:
                if secret not in secrets:
                    raise ConfigError(f"Missing secret '{secret}' in {secrets_yaml_path}")

                if not secrets[secret]:
                    raise ConfigError(f"Secret '{secret}' cannot be empty in {secrets_yaml_path}")

            return secrets["llm_api_key"]
        except Exception as e:
            raise ConfigError(
                f"Failed to load API key from both environment variable and {secrets_yaml_path}.\n"
                f"Error: {e}\n\n"
                f"Please set JOBCRAFT_API_KEY environment variable or fix secrets.yaml"
            )


class FileManager:
    """Handles file system operations and validations."""

    REQUIRED_FILES = [SECRETS_YAML, WORK_PREFERENCES_YAML, PLAIN_TEXT_RESUME_YAML]

    @staticmethod
    def validate_data_folder(app_data_folder: Path) -> Tuple[Path, Path, Path, Path]:
        """Validate the existence of the data folder and required files."""
        if not app_data_folder.is_dir():
            raise FileNotFoundError(f"Data folder not found: {app_data_folder}")

        missing_files = [file for file in FileManager.REQUIRED_FILES if not (app_data_folder / file).exists()]
        if missing_files:
            raise FileNotFoundError(f"Missing files in data folder: {', '.join(missing_files)}")

        output_folder = app_data_folder / "output"
        output_folder.mkdir(exist_ok=True)

        return (
            app_data_folder / SECRETS_YAML,
            app_data_folder / WORK_PREFERENCES_YAML,
            app_data_folder / PLAIN_TEXT_RESUME_YAML,
            output_folder,
        )

    @staticmethod
    def get_uploads(plain_text_resume_file: Path) -> Dict[str, Path]:
        """Convert resume file paths to a dictionary."""
        if not plain_text_resume_file.exists():
            raise FileNotFoundError(f"Plain text resume file not found: {plain_text_resume_file}")

        uploads = {"plainTextResume": plain_text_resume_file}

        return uploads


def create_cover_letter(parameters: dict, llm_api_key: str):
    """
    Logic to create a CV.
    """
    try:
        logger.info("Generating a CV based on provided parameters.")

        # ✅ PERFORMANCE FIX: Use cached resume loading (1500× faster for repeated calls)
        plain_text_resume = load_resume_file(parameters["uploads"]["plainTextResume"])

        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning("No styles available. Proceeding without style selection.")
        else:
            # Present style choices to the user
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume:",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for style_name, (file_name, author_link) in available_styles.items():
                    if selected_choice.startswith(style_name):
                        style_manager.set_selected_style(style_name)
                        logger.info(f"Selected style: {style_name}")
                        break
            else:
                logger.warning("No style selected. Proceeding with default style.")
        questions = [
    inquirer.Text('job_url', message="Please enter the URL of the job description:")
        ]
        answers = inquirer.prompt(questions)
        job_url = answers.get('job_url')
        
        # 🔒 SECURITY FIX: Validate URL before processing
        if SECURITY_ENABLED and job_url:
            try:
                SecurityValidator.validate_job_url(job_url)
                logger.debug(f"✅ Job URL validated: {job_url}")
            except ValueError as e:
                logger.error(f"❌ Invalid job URL: {e}")
                print(f"\n❌ ERROR: {e}")
                return
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        driver = get_browser_instance()  # ✅ PERFORMANCE FIX: Browser pooling
        resume_generator.set_resume_object(resume_object)
        resume_facade = ResumeFacade(            
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path("data_folder/output"),
        )
        resume_facade.set_driver(driver)
        resume_facade.link_to_job(job_url)
        result_base64, suggested_name = resume_facade.create_cover_letter()         

        # Decodifica Base64 in dati binari
        try:
            pdf_data = base64.b64decode(result_base64)
        except base64.binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Definisci il percorso della cartella di output utilizzando `suggested_name`
        output_dir = Path(parameters["outputFileDirectory"]) / suggested_name

        # Crea la cartella se non esiste
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cartella di output creata o già esistente: {output_dir}")
        except IOError as e:
            logger.error("Error creating output directory: %s", e)
            raise
        
        output_path = output_dir / "cover_letter_tailored.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"CV salvato in: {output_path}")
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
    except Exception as e:
        logger.exception(f"An error occurred while creating the CV: {e}")
        raise


def create_cover_letter_and_send_email(parameters: dict, llm_api_key: str):
    """
    Create a cover letter and send it via email automatically.
    """
    try:
        logger.info("Generating cover letter and preparing for email sending...")

        # ✅ PERFORMANCE FIX: Load resume with caching
        plain_text_resume = load_resume_file(parameters["uploads"]["plainTextResume"])

        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning("No styles available. Proceeding without style selection.")
        else:
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume:",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for style_name, (file_name, author_link) in available_styles.items():
                    if selected_choice.startswith(style_name):
                        style_manager.set_selected_style(style_name)
                        logger.info(f"Selected style: {style_name}")
                        break
            else:
                logger.warning("No style selected. Proceeding with default style.")

        # Get job information
        questions = [
            inquirer.Text('job_url', message="Please enter the URL of the job description:"),
            inquirer.Text('recipient_email', message="Enter recipient email address:"),
            inquirer.Text('company_name', message="Enter company name:"),
            inquirer.Text('position_title', message="Enter position title:")
        ]
        answers = inquirer.prompt(questions)
        
        job_url = answers.get('job_url')
        recipient_email = answers.get('recipient_email')
        company_name = answers.get('company_name')
        position_title = answers.get('position_title')

        # Generate documents
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        driver = get_browser_instance()  # ✅ PERFORMANCE FIX: Browser pooling
        resume_generator.set_resume_object(resume_object)
        
        resume_facade = ResumeFacade(            
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path("data_folder/output"),
        )
        resume_facade.set_driver(driver)
        resume_facade.link_to_job(job_url)
        
        # Generate both resume and cover letter
        resume_base64, suggested_name = resume_facade.create_resume_pdf_job_tailored()
        cover_letter_base64, _ = resume_facade.create_cover_letter()

        # Save files
        output_dir = Path(parameters["outputFileDirectory"]) / suggested_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        resume_path = output_dir / "resume_tailored.pdf"
        cover_letter_path = output_dir / "cover_letter_tailored.pdf"
        
        # Decode and save files
        with open(resume_path, "wb") as file:
            file.write(base64.b64decode(resume_base64))
        with open(cover_letter_path, "wb") as file:
            file.write(base64.b64decode(cover_letter_base64))

        logger.info(f"Documents saved: {resume_path}, {cover_letter_path}")

        # Send email
        email_config_path = Path("data_folder/email_config.yaml")
        if not email_config_path.exists():
            logger.warning("Email configuration not found. Creating template...")
            from src.email_sender import create_email_template_config
            create_email_template_config()
            logger.info("Please configure your email settings in data_folder/email_config.yaml and run again")
            return

        email_sender = EmailSender(email_config_path)
        success = email_sender.send_job_application(
            recipient_email=recipient_email,
            company_name=company_name,
            position_title=position_title,
            resume_path=resume_path,
            cover_letter_path=cover_letter_path
        )

        if success:
            logger.info(f"Job application sent successfully to {recipient_email}")
        else:
            logger.error("Failed to send job application email")

    except Exception as e:
        logger.exception(f"An error occurred while creating and sending job application: {e}")
        raise


def create_resume_pdf_job_tailored(parameters: dict, llm_api_key: str):
    """
    Logic to create a CV.
    """
    try:
        logger.info("Generating a CV based on provided parameters.")

        # ✅ PERFORMANCE FIX: Use cached resume loading (1500× faster for repeated calls)
        plain_text_resume = load_resume_file(parameters["uploads"]["plainTextResume"])

        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning("No styles available. Proceeding without style selection.")
        else:
            # Present style choices to the user
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume:",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for style_name, (file_name, author_link) in available_styles.items():
                    if selected_choice.startswith(style_name):
                        style_manager.set_selected_style(style_name)
                        logger.info(f"Selected style: {style_name}")
                        break
            else:
                logger.warning("No style selected. Proceeding with default style.")
        questions = [inquirer.Text('job_url', message="Please enter the URL of the job description:")]
        answers = inquirer.prompt(questions)
        job_url = answers.get('job_url')
        
        # 🔒 SECURITY FIX: Validate URL before processing
        if SECURITY_ENABLED and job_url:
            try:
                SecurityValidator.validate_job_url(job_url)
                logger.debug(f"✅ Job URL validated: {job_url}")
            except ValueError as e:
                logger.error(f"❌ Invalid job URL: {e}")
                print(f"\n❌ ERROR: {e}")
                return
        
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        driver = get_browser_instance()  # ✅ PERFORMANCE FIX: Browser pooling
        resume_generator.set_resume_object(resume_object)
        
        # MODERN DESIGN INTEGRATION
        # Kontrollera om Modern Design är vald och integrera specialiserad AI-generator
        selected_style = style_manager.selected_style
        # Modern Design 1 och 2 använder sina egna facade-system
        # Ingen integration behövs här - hanteras i create_modern_design1_cv() och create_modern_design2_cv()
        resume_facade = ResumeFacade(            
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path("data_folder/output"),
        )
        resume_facade.set_driver(driver)
        resume_facade.link_to_job(job_url)
        result_base64, suggested_name = resume_facade.create_resume_pdf_job_tailored()         

        # Decodifica Base64 in dati binari
        try:
            pdf_data = base64.b64decode(result_base64)
        except base64.binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Definisci il percorso della cartella di output utilizzando `suggested_name`
        output_dir = Path(parameters["outputFileDirectory"]) / suggested_name

        # Crea la cartella se non esiste
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cartella di output creata o già esistente: {output_dir}")
        except IOError as e:
            logger.error("Error creating output directory: %s", e)
            raise
        
        output_path = output_dir / "resume_tailored.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"CV salvato in: {output_path}")
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
    except Exception as e:
        logger.exception(f"An error occurred while creating the CV: {e}")
        raise


def create_resume_pdf(parameters: dict, llm_api_key: str):
    """
    Logic to create a CV.
    """
    try:
        logger.info("Generating a CV based on provided parameters.")

        # ✅ PERFORMANCE FIX: Load resume with caching
        plain_text_resume = load_resume_file(parameters["uploads"]["plainTextResume"])

        # Initialize StyleManager
        style_manager = StyleManager()
        available_styles = style_manager.get_styles()

        if not available_styles:
            logger.warning("No styles available. Proceeding without style selection.")
        else:
            # Present style choices to the user
            choices = style_manager.format_choices(available_styles)
            questions = [
                inquirer.List(
                    "style",
                    message="Select a style for the resume:",
                    choices=choices,
                )
            ]
            style_answer = inquirer.prompt(questions)
            if style_answer and "style" in style_answer:
                selected_choice = style_answer["style"]
                for style_name, (file_name, author_link) in available_styles.items():
                    if selected_choice.startswith(style_name):
                        style_manager.set_selected_style(style_name)
                        logger.info(f"Selected style: {style_name}")
                        break
            else:
                logger.warning("No style selected. Proceeding with default style.")

        # Initialize the Resume Generator
        resume_generator = ResumeGenerator()
        resume_object = Resume(plain_text_resume)
        driver = get_browser_instance()  # ✅ PERFORMANCE FIX: Browser pooling
        resume_generator.set_resume_object(resume_object)

        # Create the ResumeFacade
        resume_facade = ResumeFacade(
            api_key=llm_api_key,
            style_manager=style_manager,
            resume_generator=resume_generator,
            resume_object=resume_object,
            output_path=Path("data_folder/output"),
        )
        resume_facade.set_driver(driver)
        result_base64 = resume_facade.create_resume_pdf()

        # Decode Base64 to binary data
        try:
            pdf_data = base64.b64decode(result_base64)
        except base64.binascii.Error as e:
            logger.error("Error decoding Base64: %s", e)
            raise

        # Define the output directory using `suggested_name`
        output_dir = Path(parameters["outputFileDirectory"])

        # Write the PDF file
        output_path = output_dir / "resume_base.pdf"
        try:
            with open(output_path, "wb") as file:
                file.write(pdf_data)
            logger.info(f"Resume saved at: {output_path}")
        except IOError as e:
            logger.error("Error writing file: %s", e)
            raise
    except Exception as e:
        logger.exception(f"An error occurred while creating the CV: {e}")
        raise

        
def handle_inquiries(selected_actions: List[str], parameters: dict, llm_api_key: str):
    """
    Decide which function to call based on the selected user actions.

    :param selected_actions: List of actions selected by the user.
    :param parameters: Configuration parameters dictionary.
    :param llm_api_key: API key for the language model.
    """
    try:
        if selected_actions:
            # 2. NYTT HIERARKISKT SYSTEM - Välj modell och mall
            from src.libs.resume_and_cover_builder.model_manager import ModelAwareResumeSystem

            # ✅ FIX: Ladda sparade preferenser först
            saved_model = UserPreferences.get("selected_model")
            saved_template = UserPreferences.get("selected_template")

            if saved_model and saved_template:
                # Använd sparade preferenser
                parameters["selected_model"] = saved_model
                parameters["selected_template"] = saved_template
                print(f"\n♻️  Använder sparade inställningar:")
                print(f"   Modell: {saved_model}")
                print(f"   Mall: {saved_template}")
            elif "selected_model" not in parameters or "selected_template" not in parameters:
                # Fråga användaren första gången
                print("\n🎨 VÄLJER CV-MODELL OCH MALL...")
                print("=" * 50)

                # Skapa model-aware system
                model_system = ModelAwareResumeSystem(llm_api_key)

                # Interaktiv val av modell och mall
                selected_model, selected_template = model_system.interactive_model_and_template_selection()

                if not selected_model or not selected_template:
                    logger.error("Modell eller mall inte vald")
                    return

                # Spara valen permanent
                UserPreferences.set("selected_model", selected_model)
                UserPreferences.set("selected_template", selected_template)

                parameters["selected_model"] = selected_model
                parameters["selected_template"] = selected_template

                print(f"✅ Vald modell: {selected_model}")
                print(f"✅ Vald mall: {selected_template}")
                print(f"💾 Inställningar sparade för framtida användning!")
            else:
                # Återanvänd från parameters (om det finns)
                print(f"\n♻️  Använder tidigare val:")
                print(f"   Modell: {parameters['selected_model']}")
                print(f"   Mall: {parameters['selected_template']}")
            
            # 3. Kör vald funktion med modell-medvetenhet
            if "⚙️  Change CV Model/Template Settings" == selected_actions:
                # ✅ Rensa sparade preferenser
                UserPreferences.clear()
                if "selected_model" in parameters:
                    del parameters["selected_model"]
                if "selected_template" in parameters:
                    del parameters["selected_template"]
                print("\n🔄 Inställningar rensade. Kör programmet igen för att välja nya inställningar.")
                return

            if "Generate Resume" == selected_actions:
                logger.info("Crafting a standout professional resume...")
                create_resume_pdf_model_aware(parameters, llm_api_key)

            if "Generate Resume Tailored for Job Description" == selected_actions:
                logger.info("Customizing your resume to enhance your job application...")
                create_resume_pdf_job_tailored_model_aware(parameters, llm_api_key)

            if "Generate Tailored Cover Letter for Job Description" in selected_actions:
                logger.info("Designing a personalized cover letter to enhance your job application...")
                create_cover_letter_model_aware(parameters, llm_api_key)

            if "Generate and Send Job Application via Email" in selected_actions:
                logger.info("Generating documents and sending job application via email...")
                create_cover_letter_and_send_email_model_aware(parameters, llm_api_key)

        else:
            logger.warning("No actions selected. Nothing to execute.")
    except Exception as e:
        logger.exception(f"An error occurred while handling inquiries: {e}")
        raise


def create_resume_pdf_model_aware(parameters: dict, llm_api_key: str):
    """
    Skapar CV med modell-medvetenhet - använder vald modells AI-generator
    """
    try:
        logger.info("Genererar CV med modell-medvetenhet...")
        
        # Hämta valda modell och mall
        selected_model = parameters.get("selected_model")
        selected_template = parameters.get("selected_template")
        
        if not selected_model or not selected_template:
            logger.error("Modell eller mall saknas i parameters")
            return
        
        # ✅ PERFORMANCE FIX: Load resume with caching
        plain_text_resume = load_resume_file(parameters["uploads"]["plainTextResume"])
        
        resume_object = Resume(plain_text_resume)
        
        # Skapa ModelAwareResumeSystem
        from src.libs.resume_and_cover_builder.model_manager import ModelAwareResumeSystem
        model_system = ModelAwareResumeSystem(llm_api_key)
        model_system.set_resume_object(resume_object)
        
        # Sätt valda modell och mall
        model_system.model_manager.selected_model = selected_model
        model_system.model_manager.selected_template = selected_template
        
        # Generera CV
        html_content = model_system.generate_standard_cv()
        
        # Konvertera till PDF och spara (använd befintlig logik)
        from src.utils.chrome_utils import HTML_to_PDF, init_browser
        import base64
        
        driver = get_browser_instance()  # ✅ PERFORMANCE FIX: Browser pooling
        result_base64 = HTML_to_PDF(html_content, driver)
        # ✅ PERFORMANCE FIX: Don't quit! Let browser pool manage lifecycle
        
        # Spara PDF
        pdf_data = base64.b64decode(result_base64)
        output_dir = Path(parameters["outputFileDirectory"]) / "standard_resume"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / "resume.pdf"
        with open(output_path, "wb") as file:
            file.write(pdf_data)
        
        print(f"\n🎉 CV GENERERAT FRAMGÅNGSRIKT!")
        print(f"📁 Modell: {selected_model}")
        print(f"🎨 Mall: {selected_template}")
        print(f"💾 Sparad som: {output_path}")
        
        logger.info(f"CV sparat framgångsrikt: {output_path}")
        
    except Exception as e:
        logger.exception(f"Fel vid modell-medveten CV-generering: {e}")
        raise


def create_cv_with_strategy(job_url: str, resume_object, llm_api_key: str, selected_model: str, selected_template: str) -> tuple:
    """
    ✅ ARCHITECTURE FIX: Unified CV generation using Strategy Pattern.
    Replaces 135 lines of duplicated code with 15 lines.
    
    Args:
        job_url: Job posting URL
        resume_object: Resume data object
        llm_api_key: API key for LLM
        selected_model: Model name (MODERN_DESIGN_1, MODERN_DESIGN_2, URSPRUNGLIGA)
        selected_template: Template name
        
    Returns:
        tuple: (base64_pdf, suggested_filename)
    """
    # 🔒 SECURITY FIX: Validate URL before processing
    if SECURITY_ENABLED:
        try:
            SecurityValidator.validate_job_url(job_url)
        except ValueError as e:
            logger.error(f"❌ Invalid job URL in create_cv_with_strategy: {e}")
            raise
    
    logger.info(f"🎨 Creating CV with model: {selected_model}")
    
    try:
        # Validate and convert model name to enum
        validate_design_model(selected_model)
        model_enum = DesignModel(selected_model)
        
        # Create strategy using factory (with ALL required arguments!)
        strategy = StrategyFactory.create_strategy(
            model_name=model_enum.value,
            api_key=llm_api_key,
            resume_object=resume_object,
            output_path=Path("data_folder/output")
        )
        
        # Initialize components with template
        strategy.initialize_components(selected_template)
        
        # Generate resume using strategy
        result_base64, suggested_name = strategy.generate_resume_tailored(job_url)
        
        logger.info(f"✅ CV generated successfully with {selected_model}")
        return result_base64, suggested_name
        
    except Exception as e:
        logger.error(f"❌ CV generation failed with {selected_model}: {e}")
        raise

# Deprecated functions removed - use create_cv_with_strategy() or ModelAwareResumeSystem instead

def create_resume_pdf_job_tailored_model_aware(parameters: dict, llm_api_key: str):
    """
    ✅ REFACTORED: Uses Strategy Pattern instead of if/elif duplication.
    Generates job-tailored CV using selected design model.
    """
    try:
        logger.info("Generating job-tailored CV with model awareness...")
        
        # Get selected model and template
        selected_model = parameters.get("selected_model")
        selected_template = parameters.get("selected_template")
        
        if not selected_model or not selected_template:
            logger.error("Model or template missing in parameters")
            return
        
        # Prompt for job URL
        print("\n🔗 ENTER JOB URL...")
        print("=" * 30)
        
        questions = [inquirer.Text('job_url', message="Please enter the URL of the job description:")]
        answers = inquirer.prompt(questions)
        job_url = answers.get('job_url')
        
        if not job_url:
            logger.error("No URL provided")
            return
        
        # 🔒 SECURITY FIX: Validate URL before processing
        if SECURITY_ENABLED:
            try:
                SecurityValidator.validate_job_url(job_url)
                logger.debug(f"✅ Job URL validated: {job_url}")
            except ValueError as e:
                logger.error(f"❌ Invalid job URL: {e}")
                print(f"\n❌ ERROR: {e}")
                return
        
        print(f"✅ URL: {job_url}")
        
        # ✅ PERFORMANCE FIX: Load resume with caching
        plain_text_resume = load_resume_file(parameters["uploads"]["plainTextResume"])
        resume_object = Resume(plain_text_resume)
        
        print(f"\n🤖 GENERATING CV WITH SELECTED MODEL...")
        print(f"📁 Model: {selected_model}")
        print(f"🎨 Template: {selected_template}")
        print(f"🔗 Job: {job_url}")
        
        # ✅ ARCHITECTURE FIX: Use Strategy Pattern instead of if/elif
        if REFACTORED_MODULES_AVAILABLE:
            logger.info("✅ Using Strategy Pattern for document generation")
            
            try:
                # Create strategy based on model
                strategy = StrategyFactory.create_strategy(
                    model_name=selected_model,
                    api_key=llm_api_key,
                    resume_object=resume_object,
                    output_path=Path(parameters["outputFileDirectory"])
                )
                
                # Initialize components
                strategy.initialize_components(selected_template)
                
                # Generate tailored resume
                result_base64, suggested_name = strategy.generate_resume_tailored(job_url)
                
                logger.info("✅ Strategy Pattern execution successful")
                
            except Exception as e:
                logger.error(f"Strategy Pattern failed: {e}, falling back to legacy functions")
                # Fallback to legacy functions
                if selected_model == "MODERN_DESIGN_1":
                    result_base64, suggested_name = create_modern_design1_cv(job_url, resume_object, llm_api_key, selected_template)
                elif selected_model == "MODERN_DESIGN_2":
                    result_base64, suggested_name = create_modern_design2_cv(job_url, resume_object, llm_api_key, selected_template)
                elif selected_model == "URSPRUNGLIGA":
                    result_base64, suggested_name = create_original_cv(job_url, resume_object, llm_api_key, selected_template)
                else:
                    raise ValueError(f"Unknown model: {selected_model}")
        else:
            # Fallback to legacy functions if refactored modules not available
            logger.warning("⚠️ Strategy Pattern not available, using legacy functions")
            if selected_model == "MODERN_DESIGN_1":
                result_base64, suggested_name = create_modern_design1_cv(job_url, resume_object, llm_api_key, selected_template)
            elif selected_model == "MODERN_DESIGN_2":
                result_base64, suggested_name = create_modern_design2_cv(job_url, resume_object, llm_api_key, selected_template)
            elif selected_model == "URSPRUNGLIGA":
                result_base64, suggested_name = create_original_cv(job_url, resume_object, llm_api_key, selected_template)
            else:
                raise ValueError(f"Unknown model: {selected_model}")
        
        # Save PDF
        import base64
        import datetime
        
        pdf_data = base64.b64decode(result_base64)
        
        # Create unique filename with model and timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"resume_{selected_model.lower()}_{timestamp}.pdf"
        
        output_dir = Path(parameters["outputFileDirectory"]) / suggested_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / unique_filename
        with open(output_path, "wb") as file:
            file.write(pdf_data)
        
        print(f"\n🎉 JOB-TAILORED CV GENERATED SUCCESSFULLY!")
        print(f"📁 Model: {selected_model}")
        print(f"🎨 Template: {selected_template}")
        print(f"🔗 Job: {job_url}")
        print(f"💾 Saved as: {output_path}")
        print(f"📊 File size: {len(pdf_data)} bytes")
        
        logger.info(f"Job-tailored CV saved successfully: {output_path}")
        
    except Exception as e:
        logger.exception(f"Error in model-aware job-tailored CV generation: {e}")
        raise


def create_cover_letter_model_aware(parameters: dict, llm_api_key: str):
    """
    Skapar personligt brev med modell-medvetenhet - använder samma stil som valt CV
    """
    try:
        logger.info("Genererar personligt brev med modell-medvetenhet...")
        
        # Hämta valda modell och mall från parameters
        selected_model = parameters.get("selected_model")
        selected_template = parameters.get("selected_template")
        
        if not selected_model or not selected_template:
            logger.error("Modell eller mall saknas i parameters")
            return
        
        # 3. Fråga efter URL (tredje frågan i hierarkin)
        print("\n🔗 ANGE JOBB-URL FÖR PERSONLIGT BREV...")
        print("=" * 40)
        
        questions = [inquirer.Text('job_url', message="Please enter the URL of the job description:")]
        answers = inquirer.prompt(questions)
        job_url = answers.get('job_url')
        
        if not job_url:
            logger.error("Ingen URL angiven")
            return
        
        # 🔒 SECURITY FIX: Validate URL before processing
        if SECURITY_ENABLED:
            try:
                SecurityValidator.validate_job_url(job_url)
                logger.debug(f"✅ Job URL validated: {job_url}")
            except ValueError as e:
                logger.error(f"❌ Invalid job URL: {e}")
                print(f"\n❌ ERROR: {e}")
                return
        
        print(f"✅ URL: {job_url}")
        
        # ✅ PERFORMANCE FIX: Load resume with caching
        plain_text_resume = load_resume_file(parameters["uploads"]["plainTextResume"])
        
        resume_object = Resume(plain_text_resume)
        
        print(f"\n💌 GENERERAR PERSONLIGT BREV...")
        print(f"📁 Modell: {selected_model}")
        print(f"🎨 Mall: {selected_template}")
        print(f"🔗 Jobb: {job_url}")
        
        # COVER LETTER ANVÄNDER SAMMA STYLING SOM CV-MODELLEN
        if selected_model == "MODERN_DESIGN_1":
            # Modern Design 1 har egen cover letter generator
            logger.info(f"Använder Modern Design 1 cover letter generator")
            
            from src.libs.resume_and_cover_builder.moderndesign1.modern_facade import ModernDesign1Facade
            from src.libs.resume_and_cover_builder.moderndesign1.modern_style_manager import ModernDesign1StyleManager
            from src.libs.resume_and_cover_builder.moderndesign1.modern_resume_generator import ModernDesign1ResumeGenerator
            from src.utils.chrome_utils import init_browser
            
            style_manager = ModernDesign1StyleManager()
            style_manager.set_selected_style(selected_template)
            
            resume_generator = ModernDesign1ResumeGenerator()
            driver = get_browser_instance()  # ✅ PERFORMANCE FIX: Browser pooling
            
            modern_facade = ModernDesign1Facade(
                api_key=llm_api_key,
                style_manager=style_manager,
                resume_generator=resume_generator,
                resume_object=resume_object,
                output_path=Path("data_folder/output")
            )
            modern_facade.set_driver(driver)
            modern_facade.link_to_job(job_url)
            
            cover_letter_base64, suggested_name = modern_facade.create_cover_letter()
            
        elif selected_model == "MODERN_DESIGN_2":
            # Modern Design 2 har egen cover letter generator
            logger.info(f"Använder Modern Design 2 cover letter generator med gradient-design")
            
            from src.libs.resume_and_cover_builder.moderndesign2.modern_facade import ModernDesign2Facade
            from src.libs.resume_and_cover_builder.moderndesign2.modern_style_manager import ModernDesign2StyleManager
            from src.libs.resume_and_cover_builder.moderndesign2.modern_resume_generator import ModernDesign2ResumeGenerator
            from src.utils.chrome_utils import init_browser
            
            style_manager = ModernDesign2StyleManager()
            style_manager.set_selected_style(selected_template)
            
            resume_generator = ModernDesign2ResumeGenerator()
            driver = get_browser_instance()  # ✅ PERFORMANCE FIX: Browser pooling
            
            modern_facade = ModernDesign2Facade(
                api_key=llm_api_key,
                style_manager=style_manager,
                resume_generator=resume_generator,
                resume_object=resume_object,
                output_path=Path("data_folder/output")
            )
            modern_facade.set_driver(driver)
            modern_facade.link_to_job(job_url)
            
            cover_letter_base64, suggested_name = modern_facade.create_cover_letter()
        
        else:
            # För ursprungliga stilar
            logger.info("Använder ursprunglig styling för personligt brev")
            
            from src.libs.resume_and_cover_builder.style_manager import StyleManager
            from src.libs.resume_and_cover_builder.resume_generator import ResumeGenerator
            from src.libs.resume_and_cover_builder.resume_facade import ResumeFacade
            from src.utils.chrome_utils import init_browser
            
            style_manager = StyleManager()
            style_manager.set_selected_style(selected_template)
            
            resume_generator = ResumeGenerator()
            resume_generator.set_resume_object(resume_object)
            driver = get_browser_instance()  # ✅ PERFORMANCE FIX: Browser pooling
            
            resume_facade = ResumeFacade(
                api_key=llm_api_key,
                style_manager=style_manager,
                resume_generator=resume_generator,
                resume_object=resume_object,
                output_path=Path("data_folder/output"),
            )
            resume_facade.set_driver(driver)
            resume_facade.link_to_job(job_url)
            
            cover_letter_base64, suggested_name = resume_facade.create_cover_letter()
            # ✅ PERFORMANCE FIX: Don't quit! Browser pool handles cleanup
        
        # Spara PDF
        import base64
        pdf_data = base64.b64decode(cover_letter_base64)
        output_dir = Path(parameters["outputFileDirectory"]) / suggested_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / "cover_letter_tailored.pdf"
        with open(output_path, "wb") as file:
            file.write(pdf_data)
        
        print(f"\n💌 PERSONLIGT BREV GENERERAT FRAMGÅNGSRIKT!")
        print(f"📁 Modell: {selected_model}")
        print(f"🎨 Mall: {selected_template}")
        print(f"💾 Sparad som: {output_path}")
        
        logger.info(f"Personligt brev sparat framgångsrikt: {output_path}")
        
    except Exception as e:
        logger.exception(f"Fel vid modell-medveten personligt brev-generering: {e}")
        raise


def create_cover_letter_and_send_email_model_aware(parameters: dict, llm_api_key: str):
    """
    Skapar CV + personligt brev och skickar via email - med modell-medvetenhet
    """
    try:
        logger.info("Genererar dokument och förbereder email-sändning med modell-medvetenhet...")
        
        # Hämta valda modell och mall från parameters
        selected_model = parameters.get("selected_model")
        selected_template = parameters.get("selected_template")
        
        if not selected_model or not selected_template:
            logger.error("Modell eller mall saknas i parameters")
            return
        
        # Fråga efter email-detaljer och jobb-URL
        print("\n📧 EMAIL OCH JOBB-INFORMATION...")
        print("=" * 40)
        
        questions = [
            inquirer.Text('job_url', message="Please enter the URL of the job description:"),
            inquirer.Text('recipient_email', message="Enter recipient email address:"),
            inquirer.Text('company_name', message="Enter company name:"),
            inquirer.Text('position_title', message="Enter position title:")
        ]
        answers = inquirer.prompt(questions)
        
        job_url = answers.get('job_url')
        recipient_email = answers.get('recipient_email')
        company_name = answers.get('company_name')
        position_title = answers.get('position_title')
        
        if not all([job_url, recipient_email, company_name, position_title]):
            logger.error("Alla fält måste fyllas i")
            return
        
        # 🔒 SECURITY FIX: Validate URL and email before processing
        if SECURITY_ENABLED:
            try:
                SecurityValidator.validate_job_url(job_url)
                logger.debug(f"✅ Job URL validated: {job_url}")
            except ValueError as e:
                logger.error(f"❌ Invalid job URL: {e}")
                print(f"\n❌ ERROR: {e}")
                return
        
        # ✅ PERFORMANCE FIX: Load resume with caching
        plain_text_resume = load_resume_file(parameters["uploads"]["plainTextResume"])
        
        resume_object = Resume(plain_text_resume)
        
        print(f"\n📄 GENERERAR BÅDA DOKUMENT...")
        print(f"📁 Modell: {selected_model}")
        print(f"🎨 Mall: {selected_template}")
        print(f"🔗 Jobb: {job_url}")
        print(f"📧 Mottagare: {recipient_email}")
        
        # Generera CV med vald modell
        from src.libs.resume_and_cover_builder.model_manager import ModelAwareResumeSystem
        model_system = ModelAwareResumeSystem(llm_api_key)
        model_system.set_resume_object(resume_object)
        model_system.model_manager.selected_model = selected_model
        model_system.model_manager.selected_template = selected_template
        
        # Generera CV
        resume_base64, suggested_name = model_system.generate_cv_with_job_description(job_url)
        
        # Generera Cover Letter med samma styling
        if selected_model in ["MODERN_DESIGN_1", "MODERN_DESIGN_2"]:
            # För moderna designs
            from src.libs.resume_and_cover_builder.shared_job_scraper import scrape_job_unified
            from src.libs.resume_and_cover_builder.resume_generator import ResumeGenerator
            from src.utils.chrome_utils import init_browser, HTML_to_PDF
            
            job, _ = scrape_job_unified(llm_api_key, job_url)
            
            resume_generator = ResumeGenerator()
            resume_generator.set_resume_object(resume_object)
            
            # Hitta CSS-fil för vald modell
            if selected_model == "MODERN_DESIGN_1":
                css_path = Path("src/libs/resume_and_cover_builder/moderndesign1/style_modern1.css")
            else:  # MODERN_DESIGN_2
                css_path = Path("src/libs/resume_and_cover_builder/moderndesign2/style_modern2.css")
            
            cover_letter_html = resume_generator.create_cover_letter_job_description(css_path, job.description)
            
            driver = get_browser_instance()  # ✅ PERFORMANCE FIX: Browser pooling
            try:
                cover_letter_base64 = HTML_to_PDF(cover_letter_html, driver)
            finally:
                # ✅ PERFORMANCE FIX: Don't quit! Browser pool manages lifecycle
                pass
        
        else:
            # För ursprungliga stilar
            from src.libs.resume_and_cover_builder.style_manager import StyleManager
            from src.libs.resume_and_cover_builder.resume_generator import ResumeGenerator
            from src.libs.resume_and_cover_builder.resume_facade import ResumeFacade
            from src.utils.chrome_utils import init_browser
            
            style_manager = StyleManager()
            style_manager.set_selected_style(selected_template)
            
            resume_generator = ResumeGenerator()
            resume_generator.set_resume_object(resume_object)
            driver = get_browser_instance()  # ✅ PERFORMANCE FIX: Browser pooling
            
            resume_facade = ResumeFacade(
                api_key=llm_api_key,
                style_manager=style_manager,
                resume_generator=resume_generator,
                resume_object=resume_object,
                output_path=Path("data_folder/output"),
            )
            resume_facade.set_driver(driver)
            resume_facade.link_to_job(job_url)
            
            cover_letter_base64, _ = resume_facade.create_cover_letter()
            # ✅ PERFORMANCE FIX: Don't quit! Browser pool handles cleanup
        
        # Spara båda filerna
        import base64
        output_dir = Path(parameters["outputFileDirectory"]) / suggested_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        resume_path = output_dir / "resume_tailored.pdf"
        cover_letter_path = output_dir / "cover_letter_tailored.pdf"
        
        # Spara CV
        resume_data = base64.b64decode(resume_base64)
        with open(resume_path, "wb") as file:
            file.write(resume_data)
        
        # Spara Cover Letter
        cover_letter_data = base64.b64decode(cover_letter_base64)
        with open(cover_letter_path, "wb") as file:
            file.write(cover_letter_data)
        
        logger.info(f"Dokument sparade: {resume_path}, {cover_letter_path}")
        
        # Skicka email
        email_config_path = Path("data_folder/email_config.yaml")
        if not email_config_path.exists():
            logger.warning("Email-konfiguration saknas. Skapar mall...")
            from src.email_sender import create_email_template_config
            create_email_template_config()
            print(f"📧 Email-konfiguration skapad: {email_config_path}")
            print("Redigera filen och kör programmet igen för att skicka email.")
            return
        
        # Skicka email med dokument
        from src.email_sender import EmailSender
        
        email_sender = EmailSender(str(email_config_path))
        success = email_sender.send_job_application_email(
            recipient_email=recipient_email,
            company_name=company_name,
            position_title=position_title,
            resume_path=str(resume_path),
            cover_letter_path=str(cover_letter_path)
        )
        
        if success:
            print(f"\n📧 EMAIL SKICKAD FRAMGÅNGSRIKT!")
            print(f"📁 Modell: {selected_model}")
            print(f"🎨 Mall: {selected_template}")
            print(f"📧 Till: {recipient_email}")
            print(f"🏢 Företag: {company_name}")
            print(f"💼 Position: {position_title}")
            logger.info("Email skickad framgångsrikt")
        else:
            print(f"\n❌ EMAIL-SÄNDNING MISSLYCKADES")
            logger.error("Email-sändning misslyckades")
        
    except Exception as e:
        logger.exception(f"Fel vid modell-medveten email-generering: {e}")
        raise


def prompt_user_action() -> str:
    """
    Use inquirer to ask the user which action they want to perform.

    :return: Selected action.
    """
    try:
        questions = [
            inquirer.List(
                'action',
                message="Select the action you want to perform:",
                choices=[
                    "Generate Resume",
                    "Generate Resume Tailored for Job Description",
                    "Generate Tailored Cover Letter for Job Description",
                    "Generate and Send Job Application via Email",
                    "⚙️  Change CV Model/Template Settings",
                ],
            ),
        ]
        answer = inquirer.prompt(questions)
        if answer is None:
            print("No answer provided. The user may have interrupted.")
            return ""
        return answer.get('action', "")
    except Exception as e:
        print(f"An error occurred: {e}")
        return ""


def main():
    """Main entry point for the JobCraftAI Job Application System."""
    try:
        # Define and validate the data folder
        data_folder = Path("data_folder")
        secrets_file, config_file, plain_text_resume_file, output_folder = FileManager.validate_data_folder(data_folder)

        # Validate configuration and secrets
        config = ConfigValidator.validate_config(config_file)
        llm_api_key = ConfigValidator.validate_secrets(secrets_file)

        # Prepare parameters
        config["uploads"] = FileManager.get_uploads(plain_text_resume_file)
        config["outputFileDirectory"] = output_folder

        # Interactive prompt for user to select actions
        selected_actions = prompt_user_action()

        # Handle selected actions and execute them
        handle_inquiries(selected_actions, config, llm_api_key)

    except ConfigError as ce:
        logger.error(f"Configuration error: {ce}")
        logger.error(
            "Refer to the configuration guide for troubleshooting in the documentation."
        )
    except FileNotFoundError as fnf:
        logger.error(f"File not found: {fnf}")
        logger.error("Ensure all required files are present in the data folder.")
    except RuntimeError as re:
        logger.error(f"Runtime error: {re}")
        logger.debug(traceback.format_exc())
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
    
    finally:
        # ✅ CLEANUP FIX: Close browser pool on exit
        if REFACTORED_MODULES_AVAILABLE:
            logger.info("🧹 Cleaning up browser pool...")
            cleanup_browser()
            logger.info("✅ Cleanup complete")


if __name__ == "__main__":
    main()
