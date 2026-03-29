"""
Main entry point helper functions for ApplyMind AI.

Provides utility functions for resume validation, file loading,
browser management, and URL validation.
"""
import re
from pathlib import Path
from typing import Optional, Dict, Any

# Try to import refactored modules
try:
    from src.utils.browser_pool import get_browser
    from src.utils.resume_cache import load_resume_cached
    REFACTORED_MODULES_AVAILABLE = True
except ImportError:
    REFACTORED_MODULES_AVAILABLE = False

# Try to import security utilities
try:
    from src.security_utils import SecurityValidator
    SECURITY_ENABLED = True
except ImportError:
    SecurityValidator = None
    SECURITY_ENABLED = False

# Try to import browser init
try:
    from src.utils.chrome_utils import init_browser
except ImportError:
    def init_browser():
        raise RuntimeError("Browser initialization not available")


class ConfigValidator:
    """Validates configuration settings for ApplyMind AI."""

    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    REQUIRED_CONFIG_KEYS = [
        'llm_model_type',
        'llm_model',
        'job_applications_dir',
    ]

    EXPERIENCE_LEVELS = [
        'Internship',
        'Entry level',
        'Associate',
        'Mid-Senior level',
        'Director',
        'Executive',
    ]


def validate_personal_info(resume_data: Dict[str, Any]) -> bool:
    """
    Validate that resume data contains all required fields.

    Args:
        resume_data: Dictionary containing resume information

    Returns:
        True if valid

    Raises:
        ValueError: If required fields are missing or invalid
    """
    required_fields = ['plain_text', 'personal_info', 'skills', 'education', 'work_experience']
    missing = [f for f in required_fields if f not in resume_data]

    if missing:
        raise ValueError(f"Resume data missing required fields: {', '.join(missing)}")

    # Validate personal_info sub-fields
    personal_info = resume_data.get('personal_info', {})
    required_personal = ['name', 'email']
    missing_personal = [f for f in required_personal if f not in personal_info]

    if missing_personal:
        raise ValueError(f"Personal info missing required fields: {', '.join(missing_personal)}")

    # Validate email format if security is enabled
    if SECURITY_ENABLED and SecurityValidator and 'email' in personal_info:
        try:
            SecurityValidator.validate_email(personal_info['email'])
        except ValueError as e:
            raise ValueError(f"Invalid email in personal info: {e}")

    return True


def load_resume_file(file_path: Path) -> str:
    """
    Load resume content from a text file.

    Args:
        file_path: Path to the resume text file

    Returns:
        File content as string

    Raises:
        FileNotFoundError: If file does not exist
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {file_path}")

    if REFACTORED_MODULES_AVAILABLE:
        return load_resume_cached(str(file_path))

    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def get_browser_instance():
    """
    Get a browser instance, using pool if available.

    Returns:
        Selenium WebDriver instance
    """
    if REFACTORED_MODULES_AVAILABLE:
        return get_browser()
    return init_browser()


def validate_and_get_job_url() -> Optional[str]:
    """
    Prompt user for a job URL and validate it.

    Returns:
        Validated job URL string, or None if invalid/empty
    """
    try:
        import inquirer
        answers = inquirer.prompt([
            inquirer.Text('job_url', message='Enter job URL')
        ])
    except Exception:
        return None

    if not answers:
        return None

    job_url = answers.get('job_url')

    if not job_url:
        return None

    if SECURITY_ENABLED and SecurityValidator:
        try:
            SecurityValidator.validate_job_url(job_url)
        except ValueError:
            return None

    return job_url
