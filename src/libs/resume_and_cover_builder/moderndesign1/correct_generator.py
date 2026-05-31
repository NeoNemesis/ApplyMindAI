"""
Korrekt Modern Design 1 Generator baserat på användarens bild
Enkel layout med profilbild i övre högra hörnet och footer
"""

from pathlib import Path
from typing import Any, Optional
import logging
from .language_detector import detect_job_language

logger = logging.getLogger(__name__)

class CorrectModernDesign1Generator:
    """
    Generator som skapar CV enligt användarens exakta bild
    - Enkel enkolumns layout
    - Profilbild i övre högra hörnet
    - Footer med namn och titel
    """
    
    def __init__(self, resume_object: Any):
        self.resume_object = resume_object
        self.language = 'sv'  # Standard svenska
        logger.info("🎯 CorrectModernDesign1Generator initialiserad")
    
    def _get_profile_image_base64(self) -> str:
        """Hämtar profilbild som base64"""
        try:
            from .isolated_utils import image_to_base64
            
            possible_paths = [
                "data_folder/profil_no_bg.png",
                "data_folder/profil.jpg",
                "data_folder/profile.png"
            ]
            
            for path in possible_paths:
                if Path(path).exists():
                    return image_to_base64(path)
            
            logger.warning("⚠️ Ingen profilbild hittad")
            return ""
            
        except Exception as e:
            logger.error(f"❌ Fel vid profilbild: {e}")
            return ""
    
    def _get_translations(self) -> dict:
        """Returnerar översättningar för olika språk"""
        return {
            'sv': {
                'education_title': 'UTBILDNING',
                'skills_title': 'ÖVRIGA KUNSKAPER',
                'languages_title': 'SPRÅK KUNSKAPER',
                'contact_title': 'KONTAKT',
                'job_title': 'DATAINGENJÖR',
                'download_text': 'Ladda ner som PDF'
            },
            'en': {
                'education_title': 'EDUCATION',
                'skills_title': 'ADDITIONAL SKILLS',
                'languages_title': 'LANGUAGE SKILLS',
                'contact_title': 'CONTACT',
                'job_title': 'COMPUTER ENGINEER',
                'download_text': 'Download as PDF'
            }
        }
    
    def _generate_personal_info(self) -> tuple:
        """Genererar personlig information"""
        try:
            personal_info = self.resume_object.personal_information
            if not personal_info:
                return "[Name]", "DATAINGENJÖR"
            
            name = getattr(personal_info, 'name', '')
            surname = getattr(personal_info, 'surname', '')
            full_name = f"{name} {surname} C."
            
            translations = self._get_translations()[self.language]
            job_title = translations['job_title']
            
            return full_name, job_title
            
        except Exception as e:
            logger.error(f"❌ Fel vid personlig info: {e}")
            translations = self._get_translations()[self.language]
            return "[Name]", translations['job_title']
    
    def _generate_education_section(self) -> str:
        """Genererar utbildningssektion"""
        try:
            education_details = self.resume_object.education_details
            if not education_details:
                return self._get_fallback_education()
            
            html_parts = []
            for edu in education_details:
                education_level = getattr(edu, 'education_level', 'Utbildning')
                institution = getattr(edu, 'institution', 'Institution')
                
                # Anpassa för språk
                if self.language == 'en':
                    if 'Dataingenjör' in education_level:
                        education_level = 'Computer Engineering (ongoing)'
                    elif 'Programmering' in education_level:
                        education_level = 'Programming'
                    elif 'Undersköterska' in education_level:
                        education_level = 'Nursing Assistant'
                    
                    if 'Gävle Universitet' in institution:
                        institution = 'Gävle University, Uppsala University'
                    elif 'Luleå' in institution:
                        institution = 'Luleå University of Technology'
                    elif 'Lundellska' in institution:
                        institution = 'Lundellska School'
                else:
                    # Svenska - exakt som bilden
                    if 'Dataingenjör' in education_level:
                        education_level = 'Dataingenjörskap (pågående)'
                    if 'Gävle Universitet' in institution and 'Uppsala' not in institution:
                        institution = 'Gävle Universitet, Uppsala Universitet'
                
                html_parts.append(f'''<div class="education-item">
                • {education_level}<br>
                <div class="institution">{institution}</div>
            </div>''')
            
            return '\n'.join(html_parts)
            
        except Exception as e:
            logger.error(f"❌ Fel vid utbildning: {e}")
            return self._get_fallback_education()
    
    def _generate_skills_section(self) -> str:
        """Genererar kunskaper sektion"""
        if self.language == 'en':
            return '''<div class="skill-item">• Programming in Python</div>
            <div class="skill-item">• Programming in C#</div>
            <div class="skill-item">• Programming in Java</div>
            <div class="skill-item">• Database Technology in SQL</div>
            <div class="skill-item">• Extra Course in Web Design I & II</div>
            <div class="skill-item">• Microsoft Windows, Linux</div>
            <div class="skill-item">• B Driver's License</div>'''
        else:
            # Svenska - exakt som bilden
            return '''<div class="skill-item">• Programmering i Python</div>
            <div class="skill-item">• Programmering i C#</div>
            <div class="skill-item">• Programmering i Java</div>
            <div class="skill-item">• Databas teknik i SQL</div>
            <div class="skill-item">• Extra kurs inom Webbdesign I & II</div>
            <div class="skill-item">• Microsoft Windows, Linux</div>
            <div class="skill-item">• B-Körkort</div>'''
    
    def _generate_languages_section(self) -> str:
        """Genererar språk sektion"""
        if self.language == 'en':
            return '''<div class="language-item">• Swedish (Native Language)</div>
            <div class="language-item">• English (Fluent)</div>
            <div class="language-item">• Spanish (Native Language)</div>'''
        else:
            # Svenska - exakt som bilden
            return '''<div class="language-item">• Svenska (Modersmål)</div>
            <div class="language-item">• Engelska (Flytande)</div>
            <div class="language-item">• Spanska (Modersmål)</div>'''
    
    def _generate_contact_section(self) -> str:
        """Genererar kontakt sektion"""
        try:
            personal_info = self.resume_object.personal_information
            if not personal_info:
                return self._get_fallback_contact()
            
            email = getattr(personal_info, 'email', '')
            phone = getattr(personal_info, 'phone', '')
            address = getattr(personal_info, 'address', '')
            website = getattr(personal_info, 'website', '')
            
            return f'''<div class="contact-item">
                <span class="icon">📧</span>{email}
            </div>
            <div class="contact-item">
                <span class="icon">📱</span>{phone}
            </div>
            <div class="contact-item">
                <span class="icon">📍</span>{address}
            </div>
            <div class="contact-item">
                <span class="icon">🌐</span>{website}
            </div>'''
            
        except Exception as e:
            logger.error(f"❌ Fel vid kontakt: {e}")
            return self._get_fallback_contact()
    
    def _get_fallback_education(self) -> str:
        """Fallback utbildning"""
        if self.language == 'en':
            return '''<div class="education-item">
                • Computer Engineering (ongoing)<br>
                <div class="institution">Gävle University, Uppsala University</div>
            </div>
            <div class="education-item">
                • Programming<br>
                <div class="institution">Luleå University of Technology</div>
            </div>
            <div class="education-item">
                • Nursing Assistant<br>
                <div class="institution">Lundellska School</div>
            </div>'''
        else:
            return '''<div class="education-item">
                • Dataingenjörskap (pågående)<br>
                <div class="institution">Gävle Universitet, Uppsala Universitet</div>
            </div>
            <div class="education-item">
                • Programmering<br>
                <div class="institution">Luleå Tekniska Högskolan</div>
            </div>
            <div class="education-item">
                • Undersköterska<br>
                <div class="institution">Lundellska skolan</div>
            </div>'''
    
    def _get_fallback_contact(self) -> str:
        """Fallback kontakt"""
        return '''<div class="contact-item">
            <span class="icon">📧</span>email@example.com
        </div>
        <div class="contact-item">
            <span class="icon">📱</span>+46-XXX-XXX-XXX
        </div>
        <div class="contact-item">
            <span class="icon">📍</span>[Address], [City]
        </div>
        <div class="contact-item">
            <span class="icon">🌐</span>[website]
        </div>'''
    
    def generate_complete_cv_html(self, job_description: Optional[str] = None) -> str:
        """Genererar komplett CV HTML enligt användarens bild"""
        try:
            # Detektera språk
            if job_description:
                self.language = detect_job_language(job_description)
                logger.info(f"🌍 Detekterat språk: {self.language}")
            else:
                self.language = 'sv'
            
            # Generera sektioner
            education_html = self._generate_education_section()
            skills_html = self._generate_skills_section()
            languages_html = self._generate_languages_section()
            contact_html = self._generate_contact_section()
            
            # Personlig information
            full_name, job_title = self._generate_personal_info()
            
            # Profilbild
            profile_image_base64 = self._get_profile_image_base64()
            
            # Ladda template
            template_path = Path(__file__).parent / "correct_template.html"
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # Skapa body content
            translations = self._get_translations()[self.language]
            
            body_html = f'''<div class="section">
                <h3 class="section-title">{translations['education_title']}</h3>
                {education_html}
            </div>

            <div class="section">
                <h3 class="section-title">{translations['skills_title']}</h3>
                {skills_html}
            </div>

            <div class="section">
                <h3 class="section-title">{translations['languages_title']}</h3>
                {languages_html}
            </div>

            <div class="section">
                <h3 class="section-title">{translations['contact_title']}</h3>
                {contact_html}
            </div>'''
            
            # Ersätt placeholders
            from string import Template
            template_obj = Template(template)
            
            complete_html = template_obj.substitute(
                profile_image=profile_image_base64,
                body=body_html,
                full_name=full_name,
                job_title=job_title
            )
            
            logger.info(f"✅ Korrekt CV genererat på {self.language} ({len(complete_html)} tecken)")
            return complete_html
            
        except Exception as e:
            logger.error(f"❌ Fel vid CV-generering: {e}")
            raise

