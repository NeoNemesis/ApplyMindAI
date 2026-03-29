"""
Job scraping module for different platforms.
"""
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException
)
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass
import time
from loguru import logger

# Import security utilities for SSRF protection
from src.security_utils import SecurityValidator


@dataclass
class JobListing:
    """Data class for job listing information."""
    title: str
    company: str
    location: str
    description: str
    requirements: str
    url: str
    platform: str
    email: Optional[str] = None
    salary: Optional[str] = None
    posted_date: Optional[str] = None


class JobScraperBase:
    """Base class for job scrapers."""

    def __init__(self, driver=None) -> None:
        self.driver = driver
        self.platform_name = "Unknown"

    def scrape_job(self, job_url: str) -> JobListing:
        """Scrape a single job listing."""
        raise NotImplementedError("Subclasses must implement scrape_job method")

    def search_jobs(self, keywords: str, location: str, limit: int = 10) -> List[JobListing]:
        """Search for jobs on the platform."""
        raise NotImplementedError("Subclasses must implement search_jobs method")


class LinkedInScraper(JobScraperBase):
    """Scraper for LinkedIn job listings."""

    def __init__(self, driver=None) -> None:
        super().__init__(driver)
        self.platform_name = "LinkedIn"
        self.base_url = "https://www.linkedin.com"

    def scrape_job(self, job_url: str) -> JobListing:
        """Scrape LinkedIn job listing."""
        try:
            # SSRF Protection: Validate URL before scraping
            SecurityValidator.validate_job_url(job_url)

            self.driver.get(job_url)
            wait = WebDriverWait(self.driver, 10)

            # Wait for job details to load
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "jobs-unified-top-card__job-title")))

            title = self.driver.find_element(By.CLASS_NAME, "jobs-unified-top-card__job-title").text
            company = self.driver.find_element(By.CLASS_NAME, "jobs-unified-top-card__company-name").text
            location = self.driver.find_element(By.CLASS_NAME, "jobs-unified-top-card__bullet").text

            # Get job description
            description_element = self.driver.find_element(By.CLASS_NAME, "jobs-description__content")
            description = description_element.text

            return JobListing(
                title=title,
                company=company,
                location=location,
                description=description,
                requirements="",  # LinkedIn doesn't separate requirements clearly
                url=job_url,
                platform=self.platform_name
            )

        except TimeoutException as e:
            logger.error(f"Timeout while scraping LinkedIn job {job_url}: {e}")
            raise ValueError(f"Job page failed to load: {job_url}") from e
        except NoSuchElementException as e:
            logger.error(f"Required element not found on LinkedIn job {job_url}: {e}")
            raise ValueError(f"Job page structure changed or invalid: {job_url}") from e
        except (WebDriverException, ValueError) as e:
            logger.error(f"Error scraping LinkedIn job {job_url}: {e}")
            raise

    def search_jobs(self, keywords: str, location: str, limit: int = 10) -> List[JobListing]:
        """Search LinkedIn for jobs."""
        search_url = f"{self.base_url}/jobs/search/?keywords={keywords}&location={location}"

        try:
            self.driver.get(search_url)
            wait = WebDriverWait(self.driver, 10)

            # Wait for job listings to load
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "jobs-search-results__list")))

            job_links = []
            job_elements = self.driver.find_elements(By.CSS_SELECTOR, ".jobs-search-results__list-item")

            for element in job_elements[:limit]:
                try:
                    link_element = element.find_element(By.CSS_SELECTOR, "a[data-control-name='job_card_click']")
                    job_url = link_element.get_attribute("href")
                    job_links.append(job_url)
                except (AttributeError, ValueError) as e:
                    # Skip elements without proper job links
                    logger.debug(f"Skipping element without valid job link: {e}")
                    continue

            # Scrape each job
            jobs = []
            for job_url in job_links:
                try:
                    job = self.scrape_job(job_url)
                    jobs.append(job)
                    time.sleep(1)  # Be respectful to the server
                except (TimeoutException, NoSuchElementException, ValueError) as e:
                    logger.warning(f"Failed to scrape job {job_url}: {e}")
                    continue

            return jobs

        except TimeoutException as e:
            logger.error(f"Timeout while searching LinkedIn jobs: {e}")
            return []
        except (WebDriverException, ValueError) as e:
            logger.error(f"Error searching LinkedIn jobs: {e}")
            return []


class TheHubScraper(JobScraperBase):
    """Scraper for TheHub (Swedish job site)."""

    def __init__(self, driver=None) -> None:
        super().__init__(driver)
        self.platform_name = "TheHub"
        self.base_url = "https://thehub.se"

    def scrape_job(self, job_url: str) -> JobListing:
        """
        Scrape TheHub job listing.

        SECURITY: Validates URL before scraping to prevent SSRF attacks.
        RELIABILITY: Uses 10-second timeout to prevent infinite hangs on slow servers.

        Raises:
            ValueError: If URL validation fails or job page structure is invalid
            requests.Timeout: If request exceeds 10-second timeout
            requests.RequestException: For other HTTP errors
        """
        # SSRF Protection: Validate URL before scraping (outside try to preserve error message)
        SecurityValidator.validate_job_url(job_url)

        try:
            # ✅ FIX #1: Add timeout to prevent infinite hangs
            # Framework Rule: requests library best practice - always set timeout
            # Impact: Prevents application hang on slow/unresponsive servers
            response = requests.get(job_url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract job details with proper None handling (Python idiom)
            title_elem = soup.find('h1', class_='job-title')
            title = title_elem.text.strip() if title_elem else "N/A"

            company_elem = soup.find('div', class_='company-name')
            company = company_elem.text.strip() if company_elem else "N/A"

            location_elem = soup.find('div', class_='job-location')
            location = location_elem.text.strip() if location_elem else "N/A"

            description_elem = soup.find('div', class_='job-description')
            description = description_elem.text.strip() if description_elem else "N/A"

            requirements_elem = soup.find('div', class_='job-requirements')
            requirements = requirements_elem.text.strip() if requirements_elem else ""

            return JobListing(
                title=title,
                company=company,
                location=location,
                description=description,
                requirements=requirements,
                url=job_url,
                platform=self.platform_name
            )

        except requests.Timeout as e:
            logger.error(f"Request timeout (10s) scraping TheHub job {job_url}: {e}")
            raise ValueError(f"Job page timed out after 10 seconds: {job_url}") from e
        except requests.RequestException as e:
            logger.error(f"HTTP error scraping TheHub job {job_url}: {e}")
            raise ValueError(f"Failed to fetch job page: {job_url}") from e
        except (AttributeError, ValueError) as e:
            logger.error(f"Error parsing TheHub job {job_url}: {e}")
            raise ValueError(f"Job page structure changed or invalid: {job_url}") from e


class ArbetsformedlingenScraper(JobScraperBase):
    """Scraper for Arbetsförmedlingen (Swedish Employment Service)."""

    def __init__(self, driver=None) -> None:
        super().__init__(driver)
        self.platform_name = "Arbetsförmedlingen"
        self.base_url = "https://arbetsformedlingen.se"

    def scrape_job(self, job_url: str) -> JobListing:
        """
        Scrape Arbetsförmedlingen job listing.

        SECURITY: Validates URL before scraping to prevent SSRF attacks.
        RELIABILITY: Uses 10-second timeout to prevent infinite hangs on slow servers.

        Raises:
            ValueError: If URL validation fails or job page structure is invalid
            requests.Timeout: If request exceeds 10-second timeout
            requests.RequestException: For other HTTP errors
        """
        # SSRF Protection: Validate URL before scraping (outside try to preserve error message)
        SecurityValidator.validate_job_url(job_url)

        try:
            # ✅ FIX #1: Add timeout to prevent infinite hangs
            # Framework Rule: requests library best practice - always set timeout
            # Impact: Prevents application hang on slow/unresponsive servers
            response = requests.get(job_url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract title with proper None handling (Python idiom)
            title_elem = soup.find('h1', class_='job-title') or soup.find('h1')
            title = title_elem.text.strip() if title_elem else "N/A"

            company_elem = soup.find('div', class_='company-name')
            if company_elem:
                company = company_elem.text.strip()
            else:
                company_p = soup.find('p', string=lambda text: text and 'Arbetsgivare:' in text)
                company = company_p.text.replace('Arbetsgivare:', '').strip() if company_p else "N/A"

            location_elem = soup.find('div', class_='job-location')
            if location_elem:
                location = location_elem.text.strip()
            else:
                location_p = soup.find('p', string=lambda text: text and 'Ort:' in text)
                location = location_p.text.replace('Ort:', '').strip() if location_p else "N/A"

            description_div = soup.find('div', class_='job-description') or soup.find('div', {'id': 'job-description'})
            description = description_div.text.strip() if description_div else "N/A"

            requirements_elem = soup.find('div', class_='job-requirements')
            requirements = requirements_elem.text.strip() if requirements_elem else ""

            return JobListing(
                title=title,
                company=company,
                location=location,
                description=description,
                requirements=requirements,
                url=job_url,
                platform=self.platform_name
            )

        except requests.Timeout as e:
            logger.error(f"Request timeout (10s) scraping Arbetsförmedlingen job {job_url}: {e}")
            raise ValueError(f"Job page timed out after 10 seconds: {job_url}") from e
        except requests.RequestException as e:
            logger.error(f"HTTP error scraping Arbetsförmedlingen job {job_url}: {e}")
            raise ValueError(f"Failed to fetch job page: {job_url}") from e
        except (AttributeError, ValueError) as e:
            logger.error(f"Error parsing Arbetsförmedlingen job {job_url}: {e}")
            raise ValueError(f"Job page structure changed or invalid: {job_url}") from e


class JobScraperManager:
    """Manager class for different job scrapers."""

    def __init__(self, driver=None) -> None:
        self.driver = driver
        self.scrapers = {
            'linkedin': LinkedInScraper(driver),
            'thehub': TheHubScraper(driver),
            'arbetsformedlingen': ArbetsformedlingenScraper(driver)
        }

    def detect_platform(self, job_url: str) -> str:
        """Detect which platform a job URL belongs to."""
        if 'linkedin.com' in job_url:
            return 'linkedin'
        elif 'thehub.se' in job_url:
            return 'thehub'
        elif 'arbetsformedlingen.se' in job_url:
            return 'arbetsformedlingen'
        else:
            return 'unknown'

    def scrape_job(self, job_url: str) -> Optional[JobListing]:
        """Scrape job from any supported platform."""
        platform = self.detect_platform(job_url)

        if platform in self.scrapers:
            try:
                return self.scrapers[platform].scrape_job(job_url)
            except (ValueError, requests.RequestException, WebDriverException) as e:
                logger.error(f"Error scraping job from {platform}: {e}")
                return None
        else:
            logger.warning(f"Unsupported platform for URL: {job_url}")
            return None

    def search_multiple_platforms(self, keywords: str, location: str, platforms: List[str], limit_per_platform: int = 5) -> List[JobListing]:
        """Search for jobs across multiple platforms."""
        all_jobs = []

        for platform in platforms:
            if platform in self.scrapers:
                try:
                    jobs = self.scrapers[platform].search_jobs(keywords, location, limit_per_platform)
                    all_jobs.extend(jobs)
                    logger.info(f"Found {len(jobs)} jobs on {platform}")
                except (ValueError, requests.RequestException, WebDriverException, TimeoutException) as e:
                    logger.error(f"Error searching {platform}: {e}")

        return all_jobs

    def get_contact_info(self, job_listing: JobListing) -> Optional[str]:
        """Extract contact email from job listing if available."""
        # This would need to be implemented per platform
        # Some platforms don't show contact info directly
        import re

        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, job_listing.description)

        return emails[0] if emails else None


# Example usage functions
def create_job_scraper_config() -> Path:
    """Create configuration for job scraping preferences."""
    config = {
        'platforms': ['linkedin', 'thehub', 'arbetsformedlingen'],
        'search_keywords': ['python developer', 'software engineer', 'data scientist'],
        'locations': ['Stockholm', 'Göteborg', 'Malmö', 'Remote'],
        'max_jobs_per_platform': 10,
        'auto_apply': False,  # Set to True for automatic applications
        'email_delay_minutes': 5,  # Delay between email sends
    }

    import yaml
    from pathlib import Path

    config_path = Path('data_folder/job_scraper_config.yaml')
    with open(config_path, 'w', encoding='utf-8') as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)

    print(f"Job scraper configuration created at: {config_path}")
    return config_path


if __name__ == "__main__":
    # Create configuration template
    create_job_scraper_config()
