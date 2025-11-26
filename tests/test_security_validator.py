"""
Security validation tests
Tests for email validation, URL validation, and sanitization
"""
import pytest
from src.security_utils import SecurityValidator, SecurePasswordManager


class TestEmailValidation:
    """Test email address validation"""

    @pytest.mark.security
    def test_valid_email(self):
        """Test that valid email addresses pass validation"""
        valid_emails = [
            "user@example.com",
            "test.user@company.co.uk",
            "developer+jobs@gmail.com",
            "name_123@subdomain.example.org",
        ]

        for email in valid_emails:
            assert SecurityValidator.validate_email(email) is True

    @pytest.mark.security
    def test_invalid_email_format(self):
        """Test that invalid email formats are rejected"""
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "user@",
            "user@.com",
            "user name@example.com",  # Space in local part
            "",
            None,
        ]

        for email in invalid_emails:
            with pytest.raises(ValueError):
                SecurityValidator.validate_email(email)

    @pytest.mark.security
    def test_email_injection_protection(self):
        """Test protection against email header injection"""
        injection_attempts = [
            "user@example.com\nBcc: attacker@evil.com",
            "user@example.com\rSubject: Spam",
            "user@example.com; DROP TABLE users;",
            "user@example.com|cat /etc/passwd",
            "user@example.com`whoami`",
        ]

        for malicious_email in injection_attempts:
            with pytest.raises(ValueError, match="contains invalid characters"):
                SecurityValidator.validate_email(malicious_email)

    @pytest.mark.security
    def test_email_length_limit(self):
        """Test that overly long emails are rejected (RFC 5321 limit)"""
        # Create email longer than 320 characters
        long_email = "a" * 300 + "@example.com"

        with pytest.raises(ValueError, match="too long"):
            SecurityValidator.validate_email(long_email)


class TestURLValidation:
    """Test URL validation and SSRF protection"""

    @pytest.mark.security
    def test_valid_urls(self):
        """Test that valid URLs pass validation"""
        valid_urls = [
            "https://www.linkedin.com/jobs/view/123456",
            "https://careers.google.com/jobs/results",
            "http://example.com/job-posting",
        ]

        for url in valid_urls:
            assert SecurityValidator.validate_job_url(url) is True

    @pytest.mark.security
    def test_dangerous_url_schemes(self):
        """Test that dangerous URL schemes are blocked"""
        dangerous_urls = [
            "javascript:alert('XSS')",
            "file:///etc/passwd",
            "data:text/html,<script>alert('XSS')</script>",
            "ftp://internal-server/file",
        ]

        for url in dangerous_urls:
            with pytest.raises(ValueError, match="Invalid URL scheme"):
                SecurityValidator.validate_job_url(url)

    @pytest.mark.security
    def test_ssrf_protection(self):
        """Test protection against Server-Side Request Forgery (SSRF)"""
        ssrf_attempts = [
            "http://localhost/admin",
            "http://127.0.0.1/secret",
            "http://0.0.0.0/internal",
            "http://[::1]/admin",
            "http://169.254.169.254/metadata",  # AWS metadata
            "http://10.0.0.1/internal",  # Private IP
            "http://192.168.1.1/router",  # Private IP
        ]

        for url in ssrf_attempts:
            with pytest.raises(ValueError, match="Internal/localhost URLs are not allowed"):
                SecurityValidator.validate_job_url(url)

    @pytest.mark.security
    def test_invalid_url_format(self):
        """Test that malformed URLs are rejected"""
        invalid_urls = [
            "not a url",
            "htp://missing-t.com",
            "://no-scheme.com",
            "",
            None,
        ]

        for url in invalid_urls:
            with pytest.raises(ValueError):
                SecurityValidator.validate_job_url(url)


class TestSanitization:
    """Test sensitive data sanitization"""

    @pytest.mark.security
    def test_api_key_redaction(self):
        """Test that API keys are redacted in logs"""
        sensitive_text = "API key: sk-abcd1234567890efghij"
        sanitized = SecurityValidator.sanitize_for_logging(sensitive_text)

        assert "sk-abcd" not in sanitized
        assert "[API_KEY_REDACTED]" in sanitized

    @pytest.mark.security
    def test_password_redaction(self):
        """Test that passwords are redacted in logs"""
        sensitive_text = 'password="super_secret_123"'
        sanitized = SecurityValidator.sanitize_for_logging(sensitive_text)

        assert "super_secret" not in sanitized
        assert "[REDACTED]" in sanitized

    @pytest.mark.security
    def test_email_partial_redaction(self):
        """Test that emails are partially redacted (keep local part)"""
        sensitive_text = "Contact: john.doe@company.com"
        sanitized = SecurityValidator.sanitize_for_logging(sensitive_text)

        assert "john.doe@" in sanitized
        assert "company.com" not in sanitized
        assert "[REDACTED]" in sanitized


class TestSecurePasswordManager:
    """Test secure password management"""

    def test_get_api_key_from_env(self, monkeypatch):
        """Test retrieving API key from environment variable"""
        test_key = "sk-test-key-12345"
        monkeypatch.setenv("JOBCRAFT_API_KEY", test_key)

        retrieved_key = SecurePasswordManager.get_api_key()
        assert retrieved_key == test_key

    def test_get_smtp_password_from_env(self, monkeypatch):
        """Test retrieving SMTP password from environment variable"""
        test_password = "test-password-123"
        monkeypatch.setenv("JOBCRAFT_SMTP_PASSWORD", test_password)

        retrieved_password = SecurePasswordManager.get_smtp_password()
        assert retrieved_password == test_password

    def test_missing_api_key_returns_none(self, monkeypatch):
        """Test that missing API key returns None gracefully"""
        monkeypatch.delenv("JOBCRAFT_API_KEY", raising=False)

        retrieved_key = SecurePasswordManager.get_api_key()
        assert retrieved_key is None

    def test_missing_smtp_password_returns_none(self, monkeypatch):
        """Test that missing SMTP password returns None gracefully"""
        monkeypatch.delenv("JOBCRAFT_SMTP_PASSWORD", raising=False)

        retrieved_password = SecurePasswordManager.get_smtp_password()
        assert retrieved_password is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
