"""
Security utilities for ApplyMind AI
Handles sensitive data validation and sanitization
"""
import re
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from loguru import logger

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Load .env from project root
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        logger.debug(f"✅ Loaded environment variables from {env_path}")
    else:
        load_dotenv()  # Try to load from default locations
        logger.debug("Looking for .env file in current directory")
except ImportError:
    logger.warning("python-dotenv not installed. Using system environment variables only.")
except Exception as e:
    logger.warning(f"Could not load .env file: {e}")


class SecurityValidator:
    """Validates and sanitizes user inputs for security."""
    
    # Email validation regex (RFC 5322 compliant)
    EMAIL_REGEX = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )
    
    # Allowed URL schemes for job URLs
    ALLOWED_URL_SCHEMES = {'http', 'https'}
    
    @classmethod
    def validate_email(cls, email: str) -> bool:
        """
        Validate email address format.
        
        Args:
            email: Email address to validate
            
        Returns:
            bool: True if email is valid
            
        Raises:
            ValueError: If email format is invalid
        """
        if not email or not isinstance(email, str):
            raise ValueError("Email must be a non-empty string")

        # SECURITY FIX #1: Check for dangerous characters BEFORE any other validation
        # This prevents injection attacks from bypassing regex validation
        dangerous_chars = ['|', ';', '&', '$', '`', chr(10), chr(13)]  # chr(10)=newline, chr(13)=carriage return
        if any(char in email for char in dangerous_chars):
            raise ValueError("Email contains invalid characters")

        # SECURITY FIX #2: Check length BEFORE stripping (prevent bypass with whitespace)
        # RFC 5321 specifies maximum 320 characters (64 local + @ + 255 domain)
        if len(email) > 320:  # RFC 5321 max length
            raise ValueError("Email address too long (max 320 characters)")

        email = email.strip()

        # Validate email format with regex
        if not cls.EMAIL_REGEX.match(email):
            raise ValueError(
                f"Invalid email format: '{email}'. "
                "Please use format: user@example.com"
            )
        
        logger.debug(f"Email validation passed: {email}")
        return True

    @classmethod
    def validate_job_url(cls, url: str) -> bool:
        """
        Validate job URL for security.
        
        Args:
            url: URL to validate
            
        Returns:
            bool: True if URL is valid
            
        Raises:
            ValueError: If URL is invalid or potentially dangerous
        """
        if not url or not isinstance(url, str):
            raise ValueError("URL must be a non-empty string")
        
        url = url.strip()
        
        try:
            parsed = urlparse(url)
        except Exception as e:
            raise ValueError(f"Invalid URL format: {e}")
        
        # Check scheme
        if parsed.scheme not in cls.ALLOWED_URL_SCHEMES:
            raise ValueError(
                f"Invalid URL scheme: '{parsed.scheme}'. "
                f"Only {cls.ALLOWED_URL_SCHEMES} are allowed. "
                f"This prevents file:// and javascript: attacks."
            )
        
        # Check for hostname
        if not parsed.netloc:
            raise ValueError(
                f"Invalid URL: missing hostname. URL: {url}"
            )
        
        # Check for localhost/internal IPs (SSRF protection)
        localhost_patterns = [
            'localhost',
            '127.0.0.1',
            '0.0.0.0',
            '::1',
            '169.254.',  # Link-local
            '10.',       # Private Class A
            '192.168.',  # Private Class C
        ]
        
        hostname = parsed.netloc.lower()
        for pattern in localhost_patterns:
            if pattern in hostname:
                logger.warning(f"Blocked internal URL: {url}")
                raise ValueError(
                    f"Internal/localhost URLs are not allowed for security reasons"
                )
        
        logger.debug(f"URL validation passed: {url}")
        return True
    
    @classmethod
    def sanitize_for_logging(cls, text: str, sensitive_patterns: Optional[list] = None) -> str:
        """
        Sanitize sensitive information before logging.
        
        Args:
            text: Text to sanitize
            sensitive_patterns: Additional regex patterns to redact
            
        Returns:
            str: Sanitized text with sensitive data removed
        """
        if not text:
            return text
        
        sanitized = text
        
        # Default patterns to redact
        default_patterns = [
            # API keys
            (r'sk-[a-zA-Z0-9]{20,}', '[API_KEY_REDACTED]'),
            (r'api[_-]?key["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_-]+)', 'api_key=[REDACTED]'),
            
            # Passwords
            (r'password["\']?\s*[:=]\s*["\']?([^\s"\']+)', 'password=[REDACTED]'),
            (r'pwd["\']?\s*[:=]\s*["\']?([^\s"\']+)', 'pwd=[REDACTED]'),
            
            # Tokens
            (r'token["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_-]{20,})', 'token=[REDACTED]'),
            (r'bearer\s+([a-zA-Z0-9_-]+)', 'bearer [REDACTED]'),
            
            # Email addresses (partial redaction)
            (r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', r'\1@[REDACTED]'),
        ]
        
        # Add custom patterns
        if sensitive_patterns:
            default_patterns.extend(sensitive_patterns)
        
        # Apply all patterns
        for pattern, replacement in default_patterns:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        
        return sanitized


class SecurePasswordManager:
    """
    Manages passwords securely using environment variables.
    Falls back to keyring if available.
    """
    
    @staticmethod
    def get_smtp_password() -> Optional[str]:
        """
        Get SMTP password from environment variable.
        
        Returns:
            str: SMTP password or None if not found
        """
        password = os.getenv('APPLYMIND_SMTP_PASSWORD')
        
        if not password:
            logger.warning(
                "SMTP password not found in environment variables. "
                "Set APPLYMIND_SMTP_PASSWORD environment variable."
            )
            return None
        
        return password
    
    @staticmethod
    def get_api_key() -> Optional[str]:
        """
        Get API key from environment variable.
        
        Returns:
            str: API key or None if not found
        """
        api_key = os.getenv('APPLYMIND_API_KEY')
        
        if not api_key:
            logger.debug(
                "API key not found in APPLYMIND_API_KEY environment variable. "
                "Falling back to secrets.yaml"
            )
            return None
        
        return api_key
    
    @staticmethod
    def set_environment_variable_instructions() -> str:
        """Print instructions for setting environment variables."""
        instructions = """
╔════════════════════════════════════════════════════════════════╗
║          SÄKER KONFIGURATION - ENVIRONMENT VARIABLES           ║
╚════════════════════════════════════════════════════════════════╝

För att skydda dina lösenord och API-nycklar, använd environment variables:

WINDOWS (PowerShell):
---------------------
# Tillfälligt (bara för nuvarande session):
$env:APPLYMIND_SMTP_PASSWORD = "ditt-gmail-app-password"
$env:APPLYMIND_API_KEY = "din-openai-api-key"

# Permanent (lägg till i din PowerShell-profil):
[System.Environment]::SetEnvironmentVariable('APPLYMIND_SMTP_PASSWORD', 'ditt-password', 'User')
[System.Environment]::SetEnvironmentVariable('APPLYMIND_API_KEY', 'din-api-key', 'User')

LINUX/MAC (Bash):
-----------------
# Tillfälligt:
export APPLYMIND_SMTP_PASSWORD="ditt-gmail-app-password"
export APPLYMIND_API_KEY="din-openai-api-key"

# Permanent (lägg till i ~/.bashrc eller ~/.zshrc):
echo 'export APPLYMIND_SMTP_PASSWORD="ditt-password"' >> ~/.bashrc
echo 'export APPLYMIND_API_KEY="din-api-key"' >> ~/.bashrc

ALTERNATIVT: Använd .env-fil (rekommenderat för utveckling):
-------------------------------------------------------------
Skapa en .env-fil i projektets rot:

APPLYMIND_SMTP_PASSWORD=ditt-gmail-app-password
APPLYMIND_API_KEY=din-openai-api-key

VIKTIGT: Lägg till .env i .gitignore för att inte committa secrets!

════════════════════════════════════════════════════════════════
"""
        print(instructions)
        return instructions


def validate_email_batch(emails: list) -> list:
    """
    Validate multiple email addresses.
    
    Args:
        emails: List of email addresses
        
    Returns:
        list: List of valid emails
        
    Raises:
        ValueError: If any email is invalid
    """
    valid_emails = []
    invalid_emails = []
    
    for email in emails:
        try:
            SecurityValidator.validate_email(email)
            valid_emails.append(email)
        except ValueError as e:
            invalid_emails.append((email, str(e)))
    
    if invalid_emails:
        # Build error message efficiently with join (O(n) not O(n²))
        error_lines = ["Invalid emails found:"]
        error_lines.extend(f"  - {email}: {reason}" for email, reason in invalid_emails)
        error_msg = "\n".join(error_lines)
        raise ValueError(error_msg)
    return valid_emails


# Export main utilities
__all__ = [
    'SecurityValidator',
    'SecurePasswordManager',
    'validate_email_batch',
]

