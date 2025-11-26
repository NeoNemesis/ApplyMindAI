"""
Email automation module for sending job applications with generated resumes and cover letters.

SECURITY FEATURES:
- Email validation with regex
- Secure password handling via environment variables
- Input sanitization to prevent injection attacks
"""
import smtplib
import ssl
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from loguru import logger

# Import security utilities
try:
    from src.security_utils import SecurityValidator, SecurePasswordManager
except ImportError:
    logger.warning("Security utilities not available. Using basic validation.")
    SecurityValidator = None
    SecurePasswordManager = None


class EmailSender:
    """Handles automated email sending for job applications."""
    
    def __init__(self, email_config_path: Path):
        """
        Initialize EmailSender with configuration.
        
        Args:
            email_config_path: Path to email configuration YAML file
        """
        self.config = self._load_email_config(email_config_path)
        self.smtp_server = None
        
    def _load_email_config(self, config_path: Path) -> Dict:
        """
        Load email configuration from YAML file.
        
        SECURITY: Password is now loaded from environment variable instead of YAML.
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
                
            # Required fields (password is optional in config, loaded from env)
            required_fields = ['smtp_server', 'smtp_port', 'email', 'sender_name']
            for field in required_fields:
                if field not in config:
                    raise ValueError(f"Missing required field '{field}' in email config")
            
            # 🔒 SECURITY FIX: Load password from environment variable
            if SecurePasswordManager:
                env_password = SecurePasswordManager.get_smtp_password()
                if env_password:
                    config['password'] = env_password
                    logger.info("✅ SMTP password loaded from environment variable (secure)")
                elif 'password' in config:
                    logger.warning(
                        "⚠️ WARNING: Using password from YAML file (insecure). "
                        "Set JOBCRAFT_SMTP_PASSWORD environment variable instead!"
                    )
                else:
                    raise ValueError(
                        "SMTP password not found. Set JOBCRAFT_SMTP_PASSWORD "
                        "environment variable or add 'password' to email_config.yaml"
                    )
            elif 'password' not in config:
                raise ValueError("Missing 'password' field in email config")
            
            # Validate email format
            if SecurityValidator:
                try:
                    SecurityValidator.validate_email(config['email'])
                    logger.debug(f"Sender email validated: {config['email']}")
                except ValueError as e:
                    raise ValueError(f"Invalid sender email in config: {e}")
                    
            return config
        except Exception as e:
            logger.error(f"Error loading email configuration: {e}")
            raise
    
    def connect(self) -> bool:
        """Establish SMTP connection."""
        try:
            context = ssl.create_default_context()
            self.smtp_server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
            self.smtp_server.starttls(context=context)
            self.smtp_server.login(self.config['email'], self.config['password'])
            logger.info("SMTP connection established successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to SMTP server: {e}")
            return False
    
    def disconnect(self):
        """Close SMTP connection."""
        if self.smtp_server:
            self.smtp_server.quit()
            logger.info("SMTP connection closed")
    
    def send_job_application(self, 
                           recipient_email: str,
                           company_name: str,
                           position_title: str,
                           resume_path: Path,
                           cover_letter_path: Path,
                           custom_message: Optional[str] = None) -> bool:
        """
        Send job application email with resume and cover letter attachments.
        
        SECURITY: Validates email address before sending to prevent injection attacks.
        
        Args:
            recipient_email: Recipient's email address
            company_name: Name of the company
            position_title: Job position title
            resume_path: Path to generated resume PDF
            cover_letter_path: Path to generated cover letter PDF
            custom_message: Optional custom message to include
            
        Returns:
            bool: True if email sent successfully, False otherwise
            
        Raises:
            ValueError: If recipient email is invalid
        """
        # 🔒 SECURITY FIX: Validate email before sending
        if SecurityValidator:
            try:
                SecurityValidator.validate_email(recipient_email)
                logger.debug(f"✅ Recipient email validated: {recipient_email}")
            except ValueError as e:
                logger.error(f"❌ Invalid recipient email: {e}")
                raise
        
        try:
            # Create message
            msg = MIMEMultipart()

            # 🔒 SECURITY FIX: Sanitize all header fields
            safe_sender_name = self._sanitize_email_field(self.config['sender_name'])
            safe_position_title = self._sanitize_email_field(position_title)

            msg['From'] = f"{safe_sender_name} <{self.config['email']}>"
            msg['To'] = recipient_email
            msg['Subject'] = f"Ansökan till {safe_position_title} - {safe_sender_name}"
            
            # Create email body
            body = self._create_email_body(company_name, position_title, custom_message)
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # Attach resume
            if resume_path.exists():
                with open(resume_path, 'rb') as file:
                    resume_attachment = MIMEApplication(file.read(), _subtype='pdf')
                    # 🔒 SECURITY FIX: Sanitize sender_name in attachment filename
                    safe_filename = self._sanitize_email_field(self.config["sender_name"]).replace(" ", "_")
                    resume_attachment.add_header('Content-Disposition',
                                               f'attachment; filename="CV_{safe_filename}.pdf"')
                    msg.attach(resume_attachment)
                logger.info(f"Resume attached: {resume_path}")

            # Attach cover letter
            if cover_letter_path.exists():
                with open(cover_letter_path, 'rb') as file:
                    cover_attachment = MIMEApplication(file.read(), _subtype='pdf')
                    # 🔒 SECURITY FIX: Sanitize sender_name in attachment filename
                    safe_filename = self._sanitize_email_field(self.config["sender_name"]).replace(" ", "_")
                    cover_attachment.add_header('Content-Disposition',
                                              f'attachment; filename="Personligt_brev_{safe_filename}.pdf"')
                    msg.attach(cover_attachment)
                logger.info(f"Cover letter attached: {cover_letter_path}")
            
            # Send email
            if not self.smtp_server:
                if not self.connect():
                    return False
            
            self.smtp_server.send_message(msg)
            logger.info(f"Job application sent successfully to {recipient_email} for {position_title} at {company_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send job application email: {e}")
            return False
    
    def _sanitize_email_field(self, text: str) -> str:
        """
        Sanitize text to prevent email header injection.

        Removes newlines, carriage returns, and other dangerous characters
        that could be used to inject additional email headers.

        Args:
            text: Input text to sanitize

        Returns:
            Sanitized text safe for use in email headers and body
        """
        if not text:
            return ""

        # Remove newlines, carriage returns, and null bytes
        dangerous_chars = ['\n', '\r', '\0', '\x0b', '\x0c']
        sanitized = text
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, ' ')

        # Remove consecutive spaces
        while '  ' in sanitized:
            sanitized = sanitized.replace('  ', ' ')

        return sanitized.strip()

    def _create_email_body(self, company_name: str, position_title: str, custom_message: Optional[str] = None) -> str:
        """
        Create professional email body for job application.

        SECURITY: Sanitizes all user inputs to prevent header injection attacks.
        """
        # 🔒 SECURITY FIX: Sanitize inputs to prevent email header injection
        safe_company_name = self._sanitize_email_field(company_name)
        safe_position_title = self._sanitize_email_field(position_title)
        safe_sender_name = self._sanitize_email_field(self.config['sender_name'])

        base_message = f"""Hej,

Jag skickar med denna ansökan till tjänsten som {safe_position_title} på {safe_company_name}.

Bifogat finner ni mitt CV och personliga brev som är anpassade för denna specifika tjänst. Mina kvalifikationer och erfarenheter matchar väl de krav som ställs för rollen.

Jag ser fram emot att höra från er och möjligheten att diskutera hur jag kan bidra till {safe_company_name}.

Med vänliga hälsningar,
{safe_sender_name}
{self.config['email']}"""

        if custom_message:
            # Sanitize custom message but preserve intentional line breaks
            safe_custom_message = custom_message.replace('\r', '').strip()
            base_message += f"\n\nTillägg:\n{safe_custom_message}"

        return base_message
    
    def send_bulk_applications(self, applications: List[Dict]) -> Dict[str, bool]:
        """
        Send multiple job applications.
        
        Args:
            applications: List of application dictionaries containing:
                - recipient_email
                - company_name  
                - position_title
                - resume_path
                - cover_letter_path
                - custom_message (optional)
                
        Returns:
            Dict mapping application ID to success status
        """
        results = {}
        
        if not self.connect():
            logger.error("Cannot establish SMTP connection for bulk sending")
            return results
        
        try:
            for i, app in enumerate(applications):
                app_id = f"{app['company_name']}_{app['position_title']}"
                logger.info(f"Sending application {i+1}/{len(applications)}: {app_id}")
                
                success = self.send_job_application(
                    recipient_email=app['recipient_email'],
                    company_name=app['company_name'],
                    position_title=app['position_title'],
                    resume_path=Path(app['resume_path']),
                    cover_letter_path=Path(app['cover_letter_path']),
                    custom_message=app.get('custom_message')
                )
                
                results[app_id] = success
                
                # Add delay between emails to avoid being flagged as spam
                import time
                time.sleep(2)
                
        finally:
            self.disconnect()
        
        return results


def create_email_template_config():
    """Create a template email configuration file."""
    template_config = {
        'smtp_server': 'smtp.gmail.com',  # För Gmail
        'smtp_port': 587,
        'email': 'din@email.com',
        'password': 'ditt-app-lösenord',  # Använd app-specifikt lösenord för Gmail
        'sender_name': 'Ditt Fullständiga Namn',
        'signature': 'Med vänliga hälsningar,\nDitt Namn\nTelefon: +46 70 123 45 67'
    }
    
    config_path = Path('data_folder/email_config.yaml')
    with open(config_path, 'w', encoding='utf-8') as file:
        yaml.dump(template_config, file, default_flow_style=False, allow_unicode=True)
    
    print(f"Email configuration template created at: {config_path}")
    print("Please edit this file with your actual email credentials.")
    return config_path


if __name__ == "__main__":
    # Create template configuration
    create_email_template_config()
