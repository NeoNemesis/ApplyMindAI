"""
ApplyMind AI - Automated job application workflow that combines scraping, document generation, and email sending.
Built by Victor Vilches - Combining data engineering expertise with intelligent automation.
"""
import yaml
import time
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import asdict
from loguru import logger

from src.job_scrapers import JobScraperManager, JobListing
from src.email_sender import EmailSender
from src.libs.resume_and_cover_builder import ResumeFacade, ResumeGenerator, StyleManager
from src.resume_schemas.resume import Resume
from src.utils.chrome_utils import init_browser
import base64


class ApplyMindAI:
    """ApplyMind AI - Intelligent job application automation system."""
    
    def __init__(self, 
                 data_folder: Path,
                 llm_api_key: str,
                 email_config_path: Optional[Path] = None,
                 job_scraper_config_path: Optional[Path] = None):
        """
        Initialize ApplyMind AI - The intelligent job application system.
        
        Args:
            data_folder: Path to data folder containing resume and preferences
            llm_api_key: OpenAI API key for document generation
            email_config_path: Path to email configuration file
            job_scraper_config_path: Path to job scraper configuration file
        """
        self.data_folder = data_folder
        self.llm_api_key = llm_api_key
        self.output_folder = data_folder / "output"
        self.output_folder.mkdir(exist_ok=True)
        
        # Load configurations
        self.email_config_path = email_config_path or data_folder / "email_config.yaml"
        self.job_scraper_config_path = job_scraper_config_path or data_folder / "job_scraper_config.yaml"
        
        # Load resume
        resume_path = data_folder / "plain_text_resume.yaml"
        with open(resume_path, 'r', encoding='utf-8') as file:
            resume_data = yaml.safe_load(file)
        
        # Convert resume data to text format for AI processing
        self.resume_text = self._convert_resume_to_text(resume_data)
        
        # Initialize components
        self.driver = None
        self.job_scraper = None
        self.email_sender = None
        self.resume_facade = None
        
        # Statistics
        self.stats = {
            'jobs_found': 0,
            'applications_sent': 0,
            'applications_failed': 0,
            'emails_sent': 0,
            'emails_failed': 0
        }
    
    def _convert_resume_to_text(self, resume_data: Dict) -> str:
        """Convert resume YAML data to text format."""
        text_parts = []
        
        # Personal information
        if 'personal_information' in resume_data:
            personal = resume_data['personal_information']
            text_parts.append(f"Name: {personal.get('name', '')} {personal.get('surname', '')}")
            text_parts.append(f"Email: {personal.get('email', '')}")
            text_parts.append(f"Phone: {personal.get('phone', '')}")
            text_parts.append("")
        
        # Experience
        if 'experience_details' in resume_data:
            text_parts.append("EXPERIENCE:")
            for exp in resume_data['experience_details']:
                text_parts.append(f"- {exp.get('position', '')} at {exp.get('company', '')}")
                text_parts.append(f"  Period: {exp.get('employment_period', '')}")
                if 'key_responsibilities' in exp:
                    for resp in exp['key_responsibilities']:
                        text_parts.append(f"  • {resp.get('responsibility', '')}")
                text_parts.append("")
        
        # Education
        if 'education_details' in resume_data:
            text_parts.append("EDUCATION:")
            for edu in resume_data['education_details']:
                text_parts.append(f"- {edu.get('education_level', '')} in {edu.get('field_of_study', '')}")
                text_parts.append(f"  Institution: {edu.get('institution', '')}")
                text_parts.append(f"  Year: {edu.get('year_of_completion', '')}")
                text_parts.append("")
        
        # Skills (from experience)
        skills = set()
        if 'experience_details' in resume_data:
            for exp in resume_data['experience_details']:
                if 'skills_acquired' in exp:
                    skills.update(exp['skills_acquired'])
        
        if skills:
            text_parts.append("SKILLS:")
            text_parts.append(", ".join(skills))
            text_parts.append("")
        
        return "\n".join(text_parts)
    
    def initialize_components(self):
        """Initialize browser, scrapers, and other components."""
        try:
            # Initialize browser
            self.driver = init_browser()
            logger.info("Browser initialized successfully")
            
            # Initialize job scraper
            self.job_scraper = JobScraperManager(self.driver)
            logger.info("Job scraper initialized")
            
            # Initialize email sender
            if self.email_config_path.exists():
                self.email_sender = EmailSender(self.email_config_path)
                logger.info("Email sender initialized")
            else:
                logger.warning("Email configuration not found. Email functionality disabled.")
            
            # Initialize resume facade
            style_manager = StyleManager()
            available_styles = style_manager.get_styles()
            if available_styles:
                # Use first available style
                first_style = list(available_styles.keys())[0]
                style_manager.set_selected_style(first_style)
                logger.info(f"Using style: {first_style}")
            
            resume_generator = ResumeGenerator()
            resume_object = Resume(self.resume_text)
            resume_generator.set_resume_object(resume_object)
            
            self.resume_facade = ResumeFacade(
                api_key=self.llm_api_key,
                style_manager=style_manager,
                resume_generator=resume_generator,
                resume_object=resume_object,
                output_path=self.output_folder,
            )
            self.resume_facade.set_driver(self.driver)
            logger.info("Resume facade initialized")
            
        except Exception as e:
            logger.error(f"Error initializing components: {e}")
            raise
    
    def cleanup(self):
        """Clean up resources."""
        if self.driver:
            self.driver.quit()
            logger.info("Browser closed")
        
        if self.email_sender:
            self.email_sender.disconnect()
    
    def load_job_scraper_config(self) -> Dict:
        """Load job scraper configuration."""
        if not self.job_scraper_config_path.exists():
            logger.warning("Job scraper config not found. Using defaults.")
            return {
                'platforms': ['linkedin'],
                'search_keywords': ['software engineer'],
                'locations': ['Stockholm'],
                'max_jobs_per_platform': 5,
                'auto_apply': False,
                'email_delay_minutes': 5
            }
        
        with open(self.job_scraper_config_path, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)
    
    def search_jobs(self) -> List[JobListing]:
        """Search for jobs across configured platforms."""
        config = self.load_job_scraper_config()
        all_jobs = []
        
        for keyword in config['search_keywords']:
            for location in config['locations']:
                logger.info(f"Searching for '{keyword}' in '{location}'")
                
                jobs = self.job_scraper.search_multiple_platforms(
                    keywords=keyword,
                    location=location,
                    platforms=config['platforms'],
                    limit_per_platform=config['max_jobs_per_platform']
                )
                
                all_jobs.extend(jobs)
                time.sleep(2)  # Be respectful to servers
        
        # Remove duplicates based on URL
        unique_jobs = {}
        for job in all_jobs:
            if job.url not in unique_jobs:
                unique_jobs[job.url] = job
        
        unique_jobs_list = list(unique_jobs.values())
        self.stats['jobs_found'] = len(unique_jobs_list)
        logger.info(f"Found {len(unique_jobs_list)} unique jobs")
        
        return unique_jobs_list
    
    def generate_documents_for_job(self, job: JobListing) -> tuple[Path, Path]:
        """Generate tailored resume and cover letter for a job."""
        try:
            # Set job information
            self.resume_facade.link_to_job(job.url)
            
            # Generate documents
            resume_base64, suggested_name = self.resume_facade.create_resume_pdf_job_tailored()
            cover_letter_base64, _ = self.resume_facade.create_cover_letter()
            
            # Create output directory
            job_output_dir = self.output_folder / suggested_name
            job_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save files
            resume_path = job_output_dir / "resume_tailored.pdf"
            cover_letter_path = job_output_dir / "cover_letter_tailored.pdf"
            
            with open(resume_path, "wb") as file:
                file.write(base64.b64decode(resume_base64))
            
            with open(cover_letter_path, "wb") as file:
                file.write(base64.b64decode(cover_letter_base64))
            
            logger.info(f"Documents generated for {job.company} - {job.title}")
            return resume_path, cover_letter_path
            
        except Exception as e:
            logger.error(f"Error generating documents for job {job.title} at {job.company}: {e}")
            raise
    
    def apply_to_job(self, job: JobListing) -> bool:
        """Apply to a single job."""
        try:
            logger.info(f"Processing application for {job.title} at {job.company}")
            
            # Generate documents
            resume_path, cover_letter_path = self.generate_documents_for_job(job)
            
            # Try to get contact email
            contact_email = self.job_scraper.get_contact_info(job)
            
            if not contact_email:
                # You might want to implement a way to find HR emails
                # For now, we'll skip jobs without contact info
                logger.warning(f"No contact email found for {job.company} - {job.title}")
                return False
            
            # Send email if email sender is configured
            if self.email_sender:
                success = self.email_sender.send_job_application(
                    recipient_email=contact_email,
                    company_name=job.company,
                    position_title=job.title,
                    resume_path=resume_path,
                    cover_letter_path=cover_letter_path
                )
                
                if success:
                    self.stats['emails_sent'] += 1
                    self.stats['applications_sent'] += 1
                    logger.info(f"Application sent successfully to {job.company}")
                    return True
                else:
                    self.stats['emails_failed'] += 1
                    self.stats['applications_failed'] += 1
                    logger.error(f"Failed to send application to {job.company}")
                    return False
            else:
                # If no email sender, just generate documents
                logger.info(f"Documents generated for {job.company} (no email configured)")
                self.stats['applications_sent'] += 1
                return True
                
        except Exception as e:
            logger.error(f"Error applying to job {job.title} at {job.company}: {e}")
            self.stats['applications_failed'] += 1
            return False
    
    def run_automated_application_process(self, max_applications: int = 10) -> Dict:
        """Run the full automated job application process."""
        try:
            logger.info("Starting automated job application process")
            self.initialize_components()
            
            # Search for jobs
            jobs = self.search_jobs()
            
            if not jobs:
                logger.warning("No jobs found")
                return self.stats
            
            # Load configuration
            config = self.load_job_scraper_config()
            auto_apply = config.get('auto_apply', False)
            email_delay = config.get('email_delay_minutes', 5)
            
            # Apply to jobs
            applications_sent = 0
            for job in jobs[:max_applications]:
                if auto_apply:
                    success = self.apply_to_job(job)
                    if success:
                        applications_sent += 1
                        
                        # Add delay between applications
                        if applications_sent < max_applications:
                            logger.info(f"Waiting {email_delay} minutes before next application...")
                            time.sleep(email_delay * 60)
                else:
                    # Manual mode - just generate documents
                    try:
                        self.generate_documents_for_job(job)
                        self.stats['applications_sent'] += 1
                        logger.info(f"Documents prepared for manual application to {job.company}")
                    except Exception as e:
                        logger.error(f"Error preparing documents for {job.company}: {e}")
                        self.stats['applications_failed'] += 1
            
            logger.info(f"Process completed. Statistics: {self.stats}")
            return self.stats
            
        except Exception as e:
            logger.error(f"Error in automated application process: {e}")
            raise
        finally:
            self.cleanup()
    
    def save_job_applications_log(self, jobs: List[JobListing]):
        """Save a log of all job applications."""
        log_path = self.output_folder / "job_applications_log.yaml"
        
        jobs_data = []
        for job in jobs:
            job_dict = asdict(job)
            jobs_data.append(job_dict)
        
        with open(log_path, 'w', encoding='utf-8') as file:
            yaml.dump({
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'statistics': self.stats,
                'jobs': jobs_data
            }, file, default_flow_style=False, allow_unicode=True)
        
        logger.info(f"Job applications log saved to: {log_path}")


# CLI interface
def main():
    """Main CLI interface for ApplyMind AI."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ApplyMind AI - Intelligent Job Application System")
    parser.add_argument("--data-folder", type=Path, default=Path("data_folder"),
                       help="Path to data folder")
    parser.add_argument("--max-applications", type=int, default=10,
                       help="Maximum number of applications to send")
    parser.add_argument("--auto-apply", action="store_true",
                       help="Enable automatic email sending")
    
    args = parser.parse_args()
    
    # Load API key
    secrets_path = args.data_folder / "secrets.yaml"
    with open(secrets_path, 'r') as file:
        secrets = yaml.safe_load(file)
    
    llm_api_key = secrets['llm_api_key']
    
    # Create ApplyMind AI instance
    applier = ApplyMindAI(
        data_folder=args.data_folder,
        llm_api_key=llm_api_key
    )
    
    # Run process
    stats = applier.run_automated_application_process(max_applications=args.max_applications)
    
    print("\n=== FINAL STATISTICS ===")
    for key, value in stats.items():
        print(f"{key.replace('_', ' ').title()}: {value}")


if __name__ == "__main__":
    main()
