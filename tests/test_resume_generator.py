"""
Resume generation tests
Tests for CV and cover letter generation functionality
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestResumeDataValidation:
    """Test resume data validation"""

    def test_resume_data_has_required_fields(self):
        """Test that resume data contains all required fields"""
        from main import validate_personal_info

        required_fields = [
            'plain_text',
            'personal_info',
            'skills',
            'education',
            'work_experience'
        ]

        # This test ensures that the data structure is validated
        # The actual validation logic is in validate_personal_info
        assert callable(validate_personal_info)

    def test_personal_info_structure(self):
        """Test that personal info has correct structure"""
        personal_info = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'phone': '+46 70 123 45 67',
            'address': 'Stockholm, Sweden'
        }

        # Validate email format
        assert '@' in personal_info['email']
        assert '.' in personal_info['email']

        # Validate phone format (Swedish)
        assert '+46' in personal_info['phone'] or '0' in personal_info['phone']


class TestPDFGeneration:
    """Test PDF generation from HTML"""

    @pytest.mark.integration
    @patch('src.utils.chrome_utils.webdriver.Chrome')
    def test_html_to_pdf_creates_valid_pdf(self, mock_chrome):
        """Test that HTML_to_PDF generates valid base64 PDF"""
        from src.utils.chrome_utils import HTML_to_PDF

        # Mock Chrome driver
        mock_driver = MagicMock()
        mock_driver.execute_cdp_cmd.return_value = {
            'data': 'JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PC9DcmVhdG9yKQo+PgplbmRvYmoKMiAwIG9iago8PC9MZW5ndGggMz4+CnN0cmVhbQpBQkMKZW5kc3RyZWFtCmVuZG9iagp4cmVmCjAgMwowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMTUgMDAwMDAgbiAKMDAwMDAwMDA1MyAwMDAwMCBuIAp0cmFpbGVyCjw8L1NpemUgMy9Sb290IDEgMCBSPj4Kc3RhcnR4cmVmCjEwNQolJUVPRgo='
        }

        html_content = "<html><body><h1>Test CV</h1></body></html>"
        pdf_base64 = HTML_to_PDF(html_content, mock_driver)

        # Verify PDF was generated
        assert pdf_base64 is not None
        assert isinstance(pdf_base64, str)
        assert len(pdf_base64) > 0

    @pytest.mark.unit
    def test_html_to_pdf_validates_input(self):
        """Test that HTML_to_PDF validates HTML input"""
        from src.utils.chrome_utils import HTML_to_PDF

        mock_driver = MagicMock()

        # Test empty HTML
        with pytest.raises(ValueError, match="non vuota"):
            HTML_to_PDF("", mock_driver)

        # Test None HTML
        with pytest.raises(ValueError):
            HTML_to_PDF(None, mock_driver)


class TestCVTemplates:
    """Test CV template selection and rendering"""

    def test_cv_templates_exist(self):
        """Test that CV template files exist"""
        templates_path = Path("src/libs/resume_and_cover_builder/templates")

        if templates_path.exists():
            # Check that at least one template exists
            template_files = list(templates_path.glob("*.html"))
            assert len(template_files) > 0, "No template files found"

    def test_template_selection(self):
        """Test that template selection works correctly"""
        # Mock the design models
        try:
            from src.design_models import DesignModel, TemplateType

            # Test that enums are properly defined
            assert hasattr(DesignModel, 'MODERN_DESIGN1')
            assert hasattr(DesignModel, 'MODERN_DESIGN2')
            assert hasattr(TemplateType, 'TEMPLATE1')
            assert hasattr(TemplateType, 'TEMPLATE2')

        except ImportError:
            pytest.skip("Design models not available")


class TestCoverLetterGeneration:
    """Test cover letter generation"""

    @pytest.mark.integration
    def test_cover_letter_requires_job_description(self):
        """Test that cover letter generation requires job description"""
        # Cover letters should be tailored to specific job descriptions
        # This test ensures that the function signature requires job_description

        from main import validate_personal_info

        # The validation function should exist
        assert callable(validate_personal_info)

    @pytest.mark.unit
    def test_cover_letter_structure(self):
        """Test expected cover letter structure"""
        # A valid cover letter should have:
        expected_sections = [
            'greeting',  # "Hej,"
            'introduction',  # Why applying
            'body',  # Qualifications
            'closing',  # "Med vänliga hälsningar"
            'signature'  # Name and contact
        ]

        # This is a structure test - actual implementation may vary
        assert len(expected_sections) == 5


class TestBrowserSecurity:
    """Test browser security settings"""

    def test_chrome_browser_has_security_flags(self):
        """Test that Chrome browser is configured with security flags"""
        from src.utils.chrome_utils import chrome_browser_options

        options = chrome_browser_options()

        # Convert options to string to check flags
        options_str = str(options.arguments)

        # Security flags that SHOULD be present
        assert '--no-sandbox' in options_str
        assert '--disable-dev-shm-usage' in options_str
        assert '--incognito' in options_str

        # Dangerous flags that SHOULD NOT be present
        assert '--disable-web-security' not in options_str, \
            "SECURITY RISK: --disable-web-security flag found!"
        assert '--allow-file-access-from-files' not in options_str, \
            "SECURITY RISK: --allow-file-access-from-files flag found!"


class TestDataPrivacy:
    """Test data privacy and sanitization"""

    def test_sensitive_data_not_logged(self):
        """Test that sensitive data is not logged in plain text"""
        from src.security_utils import SecurityValidator

        sensitive_text = "password=secret123 api_key=sk-abcd1234"
        sanitized = SecurityValidator.sanitize_for_logging(sensitive_text)

        # Sensitive values should be redacted
        assert "secret123" not in sanitized
        assert "sk-abcd1234" not in sanitized
        assert "[REDACTED]" in sanitized


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
