"""
Email sender security tests
Tests for email header injection protection and sanitization
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.email_sender import EmailSender


@pytest.fixture
def mock_email_config(tmp_path):
    """Create a mock email configuration file"""
    config_path = tmp_path / "email_config.yaml"
    config_content = """
smtp_server: smtp.gmail.com
smtp_port: 587
email: test@example.com
password: test_password
sender_name: Test User
"""
    config_path.write_text(config_content)
    return config_path


@pytest.fixture
def email_sender(mock_email_config, monkeypatch):
    """Create EmailSender instance with mock configuration"""
    # Mock SecurePasswordManager to avoid env var requirements
    monkeypatch.setenv("JOBCRAFT_SMTP_PASSWORD", "test_password")
    return EmailSender(mock_email_config)


class TestEmailHeaderInjectionProtection:
    """Test protection against email header injection attacks"""

    @pytest.mark.security
    def test_sanitize_email_field_removes_newlines(self, email_sender):
        """Test that newlines are removed from email fields"""
        malicious_input = "Company Name\nBcc: attacker@evil.com"
        sanitized = email_sender._sanitize_email_field(malicious_input)

        assert "\n" not in sanitized
        assert "\r" not in sanitized
        assert sanitized == "Company Name Bcc: attacker@evil.com"

    @pytest.mark.security
    def test_sanitize_email_field_removes_carriage_returns(self, email_sender):
        """Test that carriage returns are removed"""
        malicious_input = "Position\rSubject: Spam Email"
        sanitized = email_sender._sanitize_email_field(malicious_input)

        assert "\r" not in sanitized
        assert sanitized == "Position Subject: Spam Email"

    @pytest.mark.security
    def test_sanitize_email_field_removes_null_bytes(self, email_sender):
        """Test that null bytes are removed"""
        malicious_input = "Company\0Name"
        sanitized = email_sender._sanitize_email_field(malicious_input)

        assert "\0" not in sanitized
        assert sanitized == "Company Name"

    @pytest.mark.security
    def test_sanitize_email_field_removes_all_dangerous_chars(self, email_sender):
        """Test that all dangerous control characters are removed"""
        # Test all dangerous characters
        malicious_input = "Text\n\r\0\x0b\x0c"
        sanitized = email_sender._sanitize_email_field(malicious_input)

        dangerous_chars = ['\n', '\r', '\0', '\x0b', '\x0c']
        for char in dangerous_chars:
            assert char not in sanitized

    @pytest.mark.security
    def test_sanitize_email_field_handles_empty_input(self, email_sender):
        """Test that empty input is handled gracefully"""
        assert email_sender._sanitize_email_field("") == ""
        assert email_sender._sanitize_email_field(None) == ""

    @pytest.mark.security
    def test_sanitize_email_field_removes_consecutive_spaces(self, email_sender):
        """Test that consecutive spaces are collapsed"""
        input_text = "Company    Name   Inc"
        sanitized = email_sender._sanitize_email_field(input_text)

        assert "  " not in sanitized  # No double spaces
        assert sanitized == "Company Name Inc"

    @pytest.mark.security
    def test_create_email_body_sanitizes_company_name(self, email_sender):
        """Test that company name is sanitized in email body"""
        malicious_company = "Evil Corp\nBcc: attacker@evil.com"
        position = "Developer"

        body = email_sender._create_email_body(malicious_company, position)

        # Check that injection was sanitized
        assert "\nBcc:" not in body
        assert "Evil Corp Bcc: attacker@evil.com" in body

    @pytest.mark.security
    def test_create_email_body_sanitizes_position_title(self, email_sender):
        """Test that position title is sanitized in email body"""
        company = "TechCorp"
        malicious_position = "Developer\rSubject: You've been hacked!"

        body = email_sender._create_email_body(company, malicious_position)

        # Check that injection was sanitized
        assert "\rSubject:" not in body
        assert "Developer Subject: You've been hacked!" in body

    @pytest.mark.security
    def test_create_email_body_sanitizes_sender_name(self, email_sender):
        """Test that sender name is sanitized in email body"""
        # Manipulate config to have malicious sender name
        email_sender.config['sender_name'] = "Attacker\nBcc: spam@evil.com"

        body = email_sender._create_email_body("Company", "Position")

        # Check that sender name in signature is sanitized
        assert "\nBcc:" not in body


class TestEmailSending:
    """Test email sending functionality"""

    @pytest.mark.integration
    @patch('src.email_sender.smtplib.SMTP')
    def test_send_job_application_validates_recipient_email(self, mock_smtp, email_sender, tmp_path):
        """Test that recipient email is validated before sending"""
        # Create dummy PDF files
        resume_path = tmp_path / "resume.pdf"
        cover_letter_path = tmp_path / "cover.pdf"
        resume_path.write_bytes(b"PDF content")
        cover_letter_path.write_bytes(b"PDF content")

        # Test with invalid email
        with pytest.raises(ValueError, match="Invalid email"):
            email_sender.send_job_application(
                recipient_email="not-an-email",
                company_name="Company",
                position_title="Developer",
                resume_path=resume_path,
                cover_letter_path=cover_letter_path
            )

    @pytest.mark.integration
    @patch('src.email_sender.smtplib.SMTP')
    def test_send_job_application_sanitizes_subject(self, mock_smtp, email_sender, tmp_path):
        """Test that email subject is sanitized"""
        # Create dummy PDF files
        resume_path = tmp_path / "resume.pdf"
        cover_letter_path = tmp_path / "cover.pdf"
        resume_path.write_bytes(b"PDF content")
        cover_letter_path.write_bytes(b"PDF content")

        # Mock SMTP
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance
        email_sender.smtp_server = mock_smtp_instance

        # Send with malicious position title
        malicious_position = "Developer\nSubject: Spam"
        email_sender.send_job_application(
            recipient_email="hr@company.com",
            company_name="Company",
            position_title=malicious_position,
            resume_path=resume_path,
            cover_letter_path=cover_letter_path
        )

        # Verify send_message was called
        assert mock_smtp_instance.send_message.called

        # Get the message that was sent
        sent_message = mock_smtp_instance.send_message.call_args[0][0]

        # Verify subject doesn't contain newlines
        assert "\n" not in sent_message['Subject']
        assert "Developer Subject: Spam" in sent_message['Subject']


class TestEmailConfiguration:
    """Test email configuration loading"""

    def test_load_email_config_requires_smtp_server(self, tmp_path):
        """Test that missing SMTP server raises error"""
        config_path = tmp_path / "bad_config.yaml"
        config_path.write_text("email: test@example.com\n")

        with pytest.raises(ValueError, match="Missing required field 'smtp_server'"):
            EmailSender(config_path)

    def test_load_email_config_validates_sender_email(self, tmp_path, monkeypatch):
        """Test that sender email is validated"""
        config_path = tmp_path / "bad_config.yaml"
        config_content = """
smtp_server: smtp.gmail.com
smtp_port: 587
email: not-an-email
password: test_password
sender_name: Test User
"""
        config_path.write_text(config_content)
        monkeypatch.setenv("JOBCRAFT_SMTP_PASSWORD", "test_password")

        with pytest.raises(ValueError, match="Invalid sender email"):
            EmailSender(config_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
