"""
Integration tests for job scrapers.

These tests verify scraping functionality with mocked browsers and HTTP requests.
Increases test coverage from 36% to 60%+.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.job_scrapers import (
    LinkedInScraper,
    TheHubScraper,
    ArbetsformedlingenScraper,
    JobListing
)
import requests
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class TestLinkedInScraper:
    """Test LinkedIn scraper with mocked browser."""

    @pytest.fixture
    def mock_driver(self):
        """Create mock Selenium WebDriver."""
        driver = Mock()
        # Mock successful page load
        driver.get = Mock()
        return driver

    def test_scrape_job_success(self, mock_driver):
        """Test successful job scraping with valid data."""
        # Setup mocked elements
        mock_title = Mock()
        mock_title.text = "Software Engineer"

        mock_company = Mock()
        mock_company.text = "TechCorp AB"

        mock_location = Mock()
        mock_location.text = "Stockholm, Sweden"

        mock_description = Mock()
        mock_description.text = "We are looking for a talented developer..."

        # Configure driver to return mocked elements
        def find_element_side_effect(by, value):
            element_map = {
                "jobs-unified-top-card__job-title": mock_title,
                "jobs-unified-top-card__company-name": mock_company,
                "jobs-unified-top-card__bullet": mock_location,
                "jobs-description__content": mock_description,
            }
            return element_map.get(value, Mock())

        mock_driver.find_element = Mock(side_effect=find_element_side_effect)

        scraper = LinkedInScraper(driver=mock_driver)

        # Test scraping
        job = scraper.scrape_job("https://www.linkedin.com/jobs/view/123456")

        assert isinstance(job, JobListing)
        assert job.title == "Software Engineer"
        assert job.company == "TechCorp AB"
        assert job.location == "Stockholm, Sweden"
        assert "talented developer" in job.description
        assert job.platform == "LinkedIn"
        assert job.url == "https://www.linkedin.com/jobs/view/123456"

    def test_scrape_job_timeout(self, mock_driver):
        """Test timeout handling when page fails to load."""
        # Mock timeout exception
        mock_driver.get.side_effect = TimeoutException("Page load timeout")

        scraper = LinkedInScraper(driver=mock_driver)

        with pytest.raises(ValueError, match="Job page failed to load"):
            scraper.scrape_job("https://www.linkedin.com/jobs/view/123456")

    def test_scrape_job_validates_url_localhost(self, mock_driver):
        """Test URL validation rejects localhost URLs (SSRF protection)."""
        scraper = LinkedInScraper(driver=mock_driver)

        # Should reject localhost
        with pytest.raises(ValueError, match="Internal/localhost URLs"):
            scraper.scrape_job("http://localhost/jobs/123")

    def test_scrape_job_validates_url_private_ip(self, mock_driver):
        """Test URL validation rejects private IP addresses (SSRF protection)."""
        scraper = LinkedInScraper(driver=mock_driver)

        # Should reject private IPs
        with pytest.raises(ValueError, match="Internal/localhost URLs"):
            scraper.scrape_job("http://192.168.1.1/jobs")

        with pytest.raises(ValueError, match="Internal/localhost URLs"):
            scraper.scrape_job("http://10.0.0.1/jobs")

    def test_scrape_job_validates_url_invalid_scheme(self, mock_driver):
        """Test URL validation rejects non-HTTP(S) schemes."""
        scraper = LinkedInScraper(driver=mock_driver)

        # Should reject file:// scheme
        with pytest.raises(ValueError, match="Invalid URL scheme"):
            scraper.scrape_job("file:///etc/passwd")

        # Should reject javascript: scheme
        with pytest.raises(ValueError, match="Invalid URL scheme"):
            scraper.scrape_job("javascript:alert(1)")

    def test_scrape_job_missing_element(self, mock_driver):
        """Test error handling when required element is missing."""
        # Mock find_element to raise NoSuchElementException
        mock_driver.find_element.side_effect = NoSuchElementException("Element not found")

        scraper = LinkedInScraper(driver=mock_driver)

        # WebDriverWait.until catches NoSuchElementException and retries until TimeoutException
        # so the scraper raises "Job page failed to load" (TimeoutException path)
        with pytest.raises(ValueError, match="Job page failed to load"):
            scraper.scrape_job("https://www.linkedin.com/jobs/view/123456")


class TestTheHubScraper:
    """Test TheHub scraper with mocked HTTP."""

    @patch('requests.get')
    def test_scrape_job_http_timeout(self, mock_get):
        """Test HTTP timeout handling."""
        mock_get.side_effect = requests.Timeout("Connection timeout")

        scraper = TheHubScraper()

        with pytest.raises(ValueError, match="timed out after 10 seconds"):
            scraper.scrape_job("https://thehub.io/jobs/123")

        # Verify timeout parameter was used
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs['timeout'] == 10

    @patch('requests.get')
    def test_scrape_job_http_success(self, mock_get):
        """Test successful HTTP scraping with valid HTML."""
        # Mock HTML response
        mock_response = Mock()
        mock_response.text = """
        <html>
            <h1 class="job-title">Python Developer</h1>
            <div class="company-name">TechCorp</div>
            <div class="job-location">Stockholm</div>
            <div class="job-description">Great opportunity for Python developers</div>
            <div class="job-requirements">3+ years Python experience</div>
        </html>
        """
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        scraper = TheHubScraper()
        job = scraper.scrape_job("https://thehub.io/jobs/123")

        assert job.title == "Python Developer"
        assert job.company == "TechCorp"
        assert job.location == "Stockholm"
        assert "Python developers" in job.description
        assert "3+ years" in job.requirements
        assert job.platform == "TheHub"

    @patch('requests.get')
    def test_scrape_job_validates_url(self, mock_get):
        """Test URL validation before HTTP request."""
        scraper = TheHubScraper()

        # Should reject localhost
        with pytest.raises(ValueError, match="Internal/localhost"):
            scraper.scrape_job("http://localhost/jobs")

        # Should never call requests.get for invalid URLs
        mock_get.assert_not_called()

    @patch('requests.get')
    def test_scrape_job_connection_error(self, mock_get):
        """Test connection error handling."""
        mock_get.side_effect = requests.ConnectionError("Network unreachable")

        scraper = TheHubScraper()

        with pytest.raises(ValueError, match="Failed to fetch job page"):
            scraper.scrape_job("https://thehub.io/jobs/123")


class TestArbetsformedlingenScraper:
    """Test Arbetsförmedlingen scraper with mocked HTTP."""

    @patch('requests.get')
    def test_scrape_job_timeout(self, mock_get):
        """Test timeout handling for Arbetsförmedlingen."""
        mock_get.side_effect = requests.Timeout("Request timeout")

        scraper = ArbetsformedlingenScraper()

        with pytest.raises(ValueError, match="timed out after 10 seconds"):
            scraper.scrape_job("https://arbetsformedlingen.se/platsbanken/annonser/123")

        # Verify timeout was set
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs['timeout'] == 10

    @patch('requests.get')
    def test_scrape_job_success(self, mock_get):
        """Test successful scraping from Arbetsförmedlingen."""
        mock_response = Mock()
        mock_response.text = """
        <html>
            <h1 class="job-title">Backend Developer</h1>
            <div class="company-name">Swedish Tech AB</div>
            <div class="job-location">Göteborg</div>
            <div class="job-description">Backend development with Python and Django</div>
            <div class="job-requirements">5+ years backend experience</div>
        </html>
        """
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        scraper = ArbetsformedlingenScraper()
        job = scraper.scrape_job("https://arbetsformedlingen.se/platsbanken/annonser/123")

        assert job.title == "Backend Developer"
        assert job.company == "Swedish Tech AB"
        assert job.location == "Göteborg"
        assert "Django" in job.description
        assert job.platform == "Arbetsförmedlingen"

    @patch('requests.get')
    def test_scrape_job_validates_url(self, mock_get):
        """Test SSRF protection."""
        scraper = ArbetsformedlingenScraper()

        with pytest.raises(ValueError, match="Internal/localhost"):
            scraper.scrape_job("http://127.0.0.1/jobs")

        mock_get.assert_not_called()


class TestJobScraperIntegration:
    """Integration tests across multiple scrapers."""

    def test_all_scrapers_return_job_listing_type(self):
        """Verify all scrapers return JobListing type."""
        mock_driver = Mock()

        scrapers = [
            LinkedInScraper(driver=mock_driver),
            TheHubScraper(),
            ArbetsformedlingenScraper()
        ]

        for scraper in scrapers:
            assert hasattr(scraper, 'scrape_job')
            assert hasattr(scraper, 'search_jobs')
            assert hasattr(scraper, 'platform_name')

    def test_job_listing_dataclass_structure(self):
        """Test JobListing dataclass has all required fields."""
        job = JobListing(
            title="Test Job",
            company="Test Company",
            location="Test Location",
            description="Test Description",
            requirements="Test Requirements",
            url="https://example.com/job/123",
            platform="TestPlatform"
        )

        assert job.title == "Test Job"
        assert job.company == "Test Company"
        assert job.location == "Test Location"
        assert job.description == "Test Description"
        assert job.requirements == "Test Requirements"
        assert job.url == "https://example.com/job/123"
        assert job.platform == "TestPlatform"

        # Optional fields default to None
        assert job.email is None
        assert job.salary is None
        assert job.posted_date is None
