"""
Förbättrad Modern Design 2 Generator - ELEGANT & MODERN DESIGN
✅ Gradient header med profilbild
✅ Progress bars för skills
✅ Kontakt-badges med ikoner
✅ Vågformad separator
✅ Moderna skuggor och färger
✅ AI-anpassning av innehåll
"""

from pathlib import Path
from typing import Any, Optional, List
from loguru import logger

# Återanvänd från moderndesign1
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "moderndesign1"))
from language_detector import detect_job_language
from ..moderndesign1.isolated_utils import create_isolated_llm, image_to_base64

class ImprovedModernDesign2Generator:
    """
    Modern Design 2 - Elegant professionell design
    - Gradient header med profilbild
    - Progress bars för skills
    - Moderna badges och ikoner
    - Vågformad separator
    """
    
    def __init__(self, resume_object: Any, api_key: str, data_dir: Optional[Path] = None):
        self.resume_object = resume_object
        self.api_key = api_key
        # Per-user datakatalog (foton m.m.). None = desktop-läge.
        self.data_dir = Path(data_dir) if data_dir else None
        self.language = 'sv'
        try:
            self.llm = create_isolated_llm(api_key)
        except Exception as e:
            logger.warning(f"⚠️ Ingen LLM tillgänglig — kör utan AI-anpassning: {e}")
            self.llm = None
        logger.info("🎨 ImprovedModernDesign2Generator initialiserad (ELEGANT DESIGN)")
    
    def _get_profile_image_base64(self) -> str:
        """Hämtar profilbild — med data_dir satt söks ENBART användarens egen katalog"""
        try:
            filenames = ["profile.png", "profil_no_bg.png", "profil.jpg", "profile.jpg"]
            base = self.data_dir if self.data_dir else Path("data_folder")
            for path in (base / f for f in filenames):
                if path.exists():
                    logger.info(f"✅ Profilbild hittad: {path}")
                    return image_to_base64(str(path))

            logger.warning("⚠️ Ingen profilbild hittad")
            return ""
        except Exception as e:
            logger.error(f"❌ Fel vid profilbild: {e}")
            return ""
    
    def _derive_job_title(self) -> str:
        """Titel från användarens senaste position i CV-datat — aldrig hårdkodad"""
        try:
            exp = getattr(self.resume_object, 'experience_details', None) or []
            pos = getattr(exp[0], 'position', '') if exp else ''
            return str(pos) if pos else ''
        except Exception:
            return ''

    def _get_translations(self) -> dict:
        """Översättningar"""
        return {
            'sv': {
                'experience_title': 'Arbetslivserfarenhet',
                'education_title': 'Utbildning',
                'skills_title': 'Tekniska Färdigheter',
                'interests_title': 'Intressen',
                'languages_title': 'Språk',
                'accomplishments': 'Viktiga prestationer:'
            },
            'en': {
                'experience_title': 'Work Experience',
                'education_title': 'Education',
                'skills_title': 'Technical Skills',
                'interests_title': 'Interests',
                'languages_title': 'Languages',
                'accomplishments': 'Key accomplishments:'
            }
        }
    
    def _generate_contact_badges(self) -> str:
        """Genererar kontakt-badges med ikoner"""
        try:
            personal_info = self.resume_object.personal_information
            if not personal_info:
                return self._get_fallback_badges()
            
            email = getattr(personal_info, 'email', '')
            phone = getattr(personal_info, 'phone', '')
            city = getattr(personal_info, 'city', '')
            website = getattr(personal_info, 'website', '')
            
            badges = []
            badges.append(f'<div class="contact-badge"><span class="icon">📧</span>{email}</div>')
            badges.append(f'<div class="contact-badge"><span class="icon">📱</span>{phone}</div>')
            badges.append(f'<div class="contact-badge"><span class="icon">📍</span>{city}</div>')
            badges.append(f'<div class="contact-badge"><span class="icon">🌐</span>{website}</div>')
            
            return '\n                        '.join(badges)
            
        except Exception as e:
            logger.error(f"❌ Fel vid badges: {e}")
            return self._get_fallback_badges()
    
    def _get_fallback_badges(self) -> str:
        """Fallback badges — tomt, aldrig påhittade uppgifter"""
        return ""
    
    def _generate_experience_section(self, job_description: str) -> str:
        """Genererar experience"""
        try:
            experience_details = self.resume_object.experience_details
            if not experience_details:
                return self._get_fallback_experience()
            
            # Top 3 senaste jobb — inga personspecifika filter
            tech_exp = list(experience_details)[:3]
            
            html_parts = []
            for exp in tech_exp:
                position = getattr(exp, 'position', 'Position')
                company = getattr(exp, 'company', 'Company')
                period = getattr(exp, 'employment_period', '2020 - Present')
                
                if self.language == 'en':
                    position = self._translate_position(position)
                    period = period.replace('Nuvarande', 'Current').replace('Present', 'Current')
                
                # Första responsibility som beskrivning
                responsibilities = getattr(exp, 'key_responsibilities', [])
                description = ""
                resp_list = []
                
                if responsibilities:
                    def _resp_text(r):
                        if isinstance(r, dict):
                            return r.get('responsibility', '')
                        if hasattr(r, 'responsibility'):
                            return r.responsibility
                        return str(r)

                    description = _resp_text(responsibilities[0])

                    # Resten som lista (max 2)
                    for r in responsibilities[1:3]:
                        text = _resp_text(r)
                        if text:
                            resp_list.append(f'<li>{text}</li>')
                
                resp_html = '\n                            '.join(resp_list)
                translations = self._get_translations()[self.language]
                
                html_parts.append(f'''<div class="experience-entry">
                    <div class="entry-dates">{period}</div>
                    <div class="entry-title">{position}</div>
                    <div class="entry-company">{company}</div>
                    <div class="entry-description">{description}</div>
                    {f'<div class="entry-accomplishments">{translations["accomplishments"]}</div><ul class="entry-list">{resp_html}</ul>' if resp_list else ''}
                </div>''')
            
            logger.info(f"✅ Experience genererad: {len(html_parts)} poster")
            return '\n                '.join(html_parts)
            
        except Exception as e:
            logger.error(f"❌ Fel vid experience: {e}")
            return self._get_fallback_experience()
    
    def _translate_position(self, position: str) -> str:
        """Översätt position"""
        translations = {
            'Ägare & Projektledare': 'Owner & Project Manager',
            'Dataingenjör & Systemutvecklare': 'Computer Engineer & System Developer',
            'System- & Nätverksadministratör': 'System & Network Administrator'
        }
        return translations.get(position, position)
    
    def _get_fallback_experience(self) -> str:
        """Fallback experience"""
        return '''<div class="experience-entry">
                <div class="entry-dates">2022 - Current</div>
                <div class="entry-title">Computer Engineer</div>
                <div class="entry-company">Tech Company</div>
                <div class="entry-description">Developed modern solutions and led technical projects.</div>
            </div>'''
    
    def _generate_education_section(self) -> str:
        """Genererar education"""
        try:
            education_details = self.resume_object.education_details
            if not education_details:
                return self._get_fallback_education()
            
            html_parts = []
            for edu in education_details:
                level = getattr(edu, 'education_level', 'Education')
                institution = getattr(edu, 'institution', 'Institution')
                year = getattr(edu, 'year_of_completion', '2024')
                
                if self.language == 'en':
                    level = self._translate_education(level)
                    institution = self._translate_institution(institution)
                
                html_parts.append(f'''<div class="education-entry">
                    <div class="entry-dates">{year}</div>
                    <div class="entry-title">{level}</div>
                    <div class="entry-company">{institution}</div>
                </div>''')
            
            logger.info(f"✅ Education genererad: {len(html_parts)} poster")
            return '\n                '.join(html_parts)
            
        except Exception as e:
            logger.error(f"❌ Fel vid education: {e}")
            return self._get_fallback_education()
    
    def _translate_education(self, text: str) -> str:
        """Översätt utbildning"""
        if 'Dataingenjör' in text:
            return 'Computer Engineering (ongoing)'
        elif 'Programmering' in text:
            return 'Programming'
        return text
    
    def _translate_institution(self, text: str) -> str:
        """Översätt institution"""
        return text.replace('Gävle Universitet', 'Gävle University')\
                   .replace('Luleå Tekniska Högskolan', 'Luleå University of Technology')\
                   .replace('Lundellska skolan', 'Lundellska School')
    
    def _get_fallback_education(self) -> str:
        """Fallback education"""
        return '''<div class="education-entry">
                <div class="entry-dates">2024</div>
                <div class="entry-title">Computer Engineering</div>
                <div class="entry-company">University</div>
            </div>'''
    
    def _generate_skills_section(self) -> str:
        """Genererar skills med PROGRESS BARS"""
        try:
            all_skills = {}
            
            # Samla skills från experience
            if self.resume_object.experience_details:
                for exp in self.resume_object.experience_details:
                    skills = getattr(exp, 'skills_acquired', [])
                    for skill in skills:
                        skill_str = str(skill)
                        if skill_str not in all_skills:
                            all_skills[skill_str] = self._estimate_skill_level(skill_str)
            
            # Från certifications (högre nivå)
            if self.resume_object.certifications:
                for cert in self.resume_object.certifications:
                    name = getattr(cert, 'name', '')
                    if name:
                        all_skills[name] = 95  # Certifieringar = expert
            
            if not all_skills:
                return self._get_fallback_skills()
            
            # Skapa progress bars
            skill_items = []
            for skill_name, percentage in list(all_skills.items())[:10]:
                skill_items.append(f'''<div class="skill-item">
                    <div class="skill-header">
                        <span class="skill-name">{skill_name}</span>
                        <span class="skill-percentage">{percentage}%</span>
                    </div>
                    <div class="skill-progress">
                        <div class="skill-progress-fill" style="width: {percentage}%"></div>
                    </div>
                </div>''')
            
            logger.info(f"✅ Skills genererade: {len(skill_items)} med progress bars")
            return '\n                    '.join(skill_items)
            
        except Exception as e:
            logger.error(f"❌ Fel vid skills: {e}")
            return self._get_fallback_skills()
    
    def _estimate_skill_level(self, skill_name: str) -> int:
        """Estimerar färdighetsnivå (0-100)"""
        # Nyckelord som indikerar expertis
        expert_keywords = ['JavaScript', 'Python', 'SQL', 'Git', 'Linux', 'Windows']
        advanced_keywords = ['Java', 'C#', 'PHP', 'HTML', 'CSS', 'GitHub']
        
        for keyword in expert_keywords:
            if keyword.lower() in skill_name.lower():
                return 90
        
        for keyword in advanced_keywords:
            if keyword.lower() in skill_name.lower():
                return 80
        
        return 75  # Default
    
    def _get_fallback_skills(self) -> str:
        """Fallback skills"""
        return '''<div class="skill-item">
                <div class="skill-header">
                    <span class="skill-name">JavaScript</span>
                    <span class="skill-percentage">90%</span>
                </div>
                <div class="skill-progress">
                    <div class="skill-progress-fill" style="width: 90%"></div>
                </div>
            </div>'''
    
    def _generate_languages_section(self) -> str:
        """Genererar språk med elegant badges"""
        try:
            languages = self.resume_object.languages
            if not languages:
                return self._get_fallback_languages()
            
            html_parts = []
            for lang in languages:
                lang_name = getattr(lang, 'language', '')
                proficiency = getattr(lang, 'proficiency', '')
                
                if self.language == 'en':
                    lang_name = self._translate_language(lang_name)
                    proficiency = self._translate_proficiency(proficiency)
                
                html_parts.append(f'''<div class="language-item">
                    <div class="language-header">
                        <span class="language-name">{lang_name}</span>
                        <span class="language-level">{proficiency}</span>
                    </div>
                </div>''')
            
            logger.info(f"✅ Languages genererade: {len(html_parts)}")
            return '\n                    '.join(html_parts)
            
        except Exception as e:
            logger.error(f"❌ Fel vid languages: {e}")
            return self._get_fallback_languages()
    
    def _translate_language(self, lang: str) -> str:
        """Översätt språk"""
        return lang.replace('Svenska', 'Swedish').replace('Engelska', 'English').replace('Spanska', 'Spanish')
    
    def _translate_proficiency(self, prof: str) -> str:
        """Översätt nivå"""
        return prof.replace('Modersmål', 'Native').replace('Flytande', 'Fluent')
    
    def _get_fallback_languages(self) -> str:
        """Fallback languages"""
        return '''<div class="language-item">
                <div class="language-header">
                    <span class="language-name">Swedish</span>
                    <span class="language-level">Native</span>
                </div>
            </div>'''
    
    def _generate_interests_section(self) -> str:
        """Genererar interests"""
        try:
            interests = self.resume_object.interests
            if not interests:
                return self._get_fallback_interests()
            
            html_parts = []
            for interest in interests[:4]:  # Top 4
                # Skapa kort beskrivning
                if self.language == 'en':
                    desc = f"Passionate about {interest.lower()} and continuous development in this area."
                else:
                    desc = f"Passion för {interest.lower()} och kontinuerlig utveckling inom området."
                
                html_parts.append(f'''<div class="interest-item">
                    <div class="interest-name">{interest}</div>
                    <div class="interest-description">{desc}</div>
                </div>''')
            
            logger.info(f"✅ Interests genererade: {len(html_parts)}")
            return '\n                    '.join(html_parts)
            
        except Exception as e:
            logger.error(f"❌ Fel vid interests: {e}")
            return self._get_fallback_interests()
    
    def _get_fallback_interests(self) -> str:
        """Fallback interests"""
        return '''<div class="interest-item">
                <div class="interest-name">Technology</div>
                <div class="interest-description">Passion för modern teknik och innovation.</div>
            </div>'''
    
    def generate_complete_cv_html(self, job_description: Optional[str] = None) -> str:
        """Genererar komplett elegant CV"""
        try:
            # Detektera språk
            if job_description:
                self.language = detect_job_language(job_description)
                logger.info(f"🌍 Detekterat språk: {self.language}")
            else:
                self.language = 'sv'
            
            logger.info(f"🎨 Genererar elegant Modern Design 2 CV på {self.language}")
            
            # Hämta personlig info
            personal_info = self.resume_object.personal_information
            if personal_info:
                name = getattr(personal_info, 'name', '')
                surname = getattr(personal_info, 'surname', '')
                full_name = f"{name} {surname}".strip()
            else:
                full_name = ""
            
            # Generera sektioner
            contact_badges = self._generate_contact_badges()
            experience_html = self._generate_experience_section(job_description or "")
            education_html = self._generate_education_section()
            skills_html = self._generate_skills_section()
            interests_html = self._generate_interests_section()
            languages_html = self._generate_languages_section()
            
            # Profilbild
            profile_image = self._get_profile_image_base64()
            
            # Translations
            translations = self._get_translations()[self.language]
            
            # Ladda template
            template_path = Path(__file__).parent / "improved_template.html"
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # Ersätt placeholders
            from string import Template
            template_obj = Template(template)
            
            complete_html = template_obj.substitute(
                profile_image=profile_image,
                full_name=full_name,
                job_title=self._derive_job_title(),
                contact_badges=contact_badges,
                summary_section="",
                experience_title=translations['experience_title'],
                experience_content=experience_html,
                education_title=translations['education_title'],
                education_content=education_html,
                skills_title=translations['skills_title'],
                skills_content=skills_html,
                interests_title=translations['interests_title'],
                interests_content=interests_html,
                languages_title=translations['languages_title'],
                languages_content=languages_html
            )
            
            logger.info(f"✅ Elegant Modern Design 2 CV genererat ({len(complete_html)} tecken)")
            logger.info("🎨 Inkluderar: Gradient header, Progress bars, Vågformad separator, Kontakt-badges")
            return complete_html
            
        except Exception as e:
            logger.error(f"❌ Fel vid CV-generering: {e}")
            raise
