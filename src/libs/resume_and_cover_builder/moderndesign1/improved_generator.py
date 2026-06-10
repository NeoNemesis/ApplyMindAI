"""
Förbättrad Modern Design 1 Generator - KOMPLETT OMARBETAD VERSION
✅ Läser RIKTIG data från resume_object
✅ AI-anpassning av erfarenheter
✅ Dynamiska språk, kunskaper och kontakt
✅ Fallback-system för säkerhet
"""

from pathlib import Path
from typing import Any, Optional, List, Dict
from loguru import logger
from .language_detector import detect_job_language
from .isolated_utils import create_isolated_llm, image_to_base64

class ImprovedModernDesign1Generator:
    """
    Förbättrad generator som skapar CV enligt exakt design från bilden
    - Tvåkolumns layout (35% vänster, 65% höger)
    - Läser RIKTIG data från resume_object
    - AI-anpassning för jobbspecifikt innehåll
    - Språkdetektering och automatisk översättning
    """
    
    def __init__(self, resume_object: Any, api_key: str):
        self.resume_object = resume_object
        self.api_key = api_key
        self.language = 'sv'  # Standard svenska
        try:
            self.llm = create_isolated_llm(api_key)
        except Exception as e:
            logger.warning(f"⚠️ Ingen LLM tillgänglig — kör utan AI-anpassning: {e}")
            self.llm = None
        logger.info("🎯 ImprovedModernDesign1Generator initialiserad (FÖRBÄTTRAD VERSION)")

    def _get_profile_image_base64(self) -> str:
        """Hämtar profilbild som base64"""
        try:
            possible_paths = [
                "data_folder/profile.png",
                "data_folder/profil_no_bg.png",
                "data_folder/profil.jpg",
                "data_folder/profile.jpg",
            ]
            
            for path in possible_paths:
                if Path(path).exists():
                    logger.info(f"✅ Profilbild hittad: {path}")
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
                'experience_title': 'YRKESERFARENHET & KOMPETENSER',
                'technical_skills_title': 'Tekniska Färdigheter',
                'job_title': 'SYSTEMUTVECKLARE | FULLSTACKUTVECKLARE',
                'download_text': 'Ladda ner som PDF'
            },
            'en': {
                'education_title': 'EDUCATION',
                'skills_title': 'ADDITIONAL SKILLS',
                'languages_title': 'LANGUAGE SKILLS',
                'contact_title': 'CONTACT',
                'experience_title': 'PROFESSIONAL EXPERIENCE & COMPETENCIES',
                'technical_skills_title': 'Technical Skills',
                'job_title': 'SYSTEM DEVELOPER | FULLSTACK DEVELOPER',
                'download_text': 'Download as PDF'
            }
        }
    
    def _generate_personal_info(self) -> tuple:
        """Genererar personlig information från RIKTIG data"""
        try:
            personal_info = self.resume_object.personal_information
            if not personal_info:
                logger.warning("⚠️ Ingen personlig information hittad, använder fallback")
                return self._get_fallback_personal_info()
            
            name = getattr(personal_info, 'name', 'Victor')
            surname = getattr(personal_info, 'surname', 'Vilches')
            full_name = f"{name} {surname} C."
            
            translations = self._get_translations()[self.language]
            job_title = translations['job_title']
            
            # Generera sammanfattning baserat på språk
            summary = self._get_default_summary()
            
            logger.info(f"✅ Personlig info genererad: {full_name}")
            return full_name, job_title, summary
            
        except Exception as e:
            logger.error(f"❌ Fel vid personlig info: {e}")
            return self._get_fallback_personal_info()
    
    def _get_fallback_personal_info(self) -> tuple:
        """Fallback personlig info"""
        translations = self._get_translations()[self.language]
        return "", translations['job_title'], self._get_default_summary()
    
    def _get_default_summary(self) -> str:
        """Returnerar sammanfattning från YAML professional_summary"""
        try:
            # Hämta professional_summary från YAML
            professional_summary = getattr(self.resume_object, 'professional_summary', '')
            if professional_summary:
                # Översätt till engelska om nödvändigt (eller använd som den är)
                if self.language == 'en':
                    # För engelska, översätt eller använd en engelsk version
                    return "Curious system developer with broad foundational knowledge in several technical areas. Specialized in system integration and Windows environments with experience in programming, databases and web design. Values teamwork and knowledge sharing, works both independently and in collaboration with others. Driving force: continuous development and solving technical challenges."
                else:
                    return professional_summary
            else:
                # Fallback om professional_summary saknas
                logger.warning("⚠️ Ingen professional_summary hittad, använder fallback")
                if self.language == 'en':
                    return "Curious system developer with broad foundational knowledge in several technical areas."
                else:
                    return "Nyfiken systemutvecklare med breda grundkunskaper inom flera tekniska områden."
        except Exception as e:
            logger.error(f"❌ Fel vid hämtning av professional_summary: {e}")
            if self.language == 'en':
                return "Curious system developer with broad foundational knowledge in several technical areas."
            else:
                return "Nyfiken systemutvecklare med breda grundkunskaper inom flera tekniska områden."
    
    def _generate_education_section(self) -> str:
        """Genererar utbildningssektion från RIKTIG data"""
        try:
            education_details = self.resume_object.education_details
            if not education_details:
                logger.warning("⚠️ Ingen utbildning hittad, använder fallback")
                return self._get_fallback_education()
            
            html_parts = []
            for edu in education_details:
                education_level = getattr(edu, 'education_level', 'Utbildning')
                institution = getattr(edu, 'institution', 'Institution')
                
                # Översätt baserat på språk
                if self.language == 'en':
                    education_level = self._translate_education_to_english(education_level)
                    institution = self._translate_institution_to_english(institution)
                
                html_parts.append(f'''<div class="education-item">
                • {education_level}<br>
                <div class="institution">{institution}</div>
            </div>''')
            
            logger.info(f"✅ Utbildning genererad: {len(html_parts)} poster")
            return '\n            '.join(html_parts)
            
        except Exception as e:
            logger.error(f"❌ Fel vid utbildning: {e}")
            return self._get_fallback_education()
    
    def _translate_education_to_english(self, edu_text: str) -> str:
        """Översätt utbildningsnivå till engelska"""
        translations = {
            'Dataingenjör': 'Computer Engineering (ongoing)',
            'Programmering': 'Programming',
            'Undersköterska': 'Nursing Assistant'
        }
        for sv, en in translations.items():
            if sv in edu_text:
                return en
        return edu_text
    
    def _translate_institution_to_english(self, inst_text: str) -> str:
        """Översätt institution till engelska"""
        translations = {
            'Gävle Universitet': 'Gävle University',
            'Uppsala Universitet': 'Uppsala University',
            'Luleå Tekniska Högskolan': 'Luleå University of Technology',
            'Lundellska skolan': 'Lundellska School'
        }
        result = inst_text
        for sv, en in translations.items():
            result = result.replace(sv, en)
        return result
    
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
    
    def _generate_skills_section(self) -> str:
        """Genererar kunskaper från RIKTIG data (certifications)"""
        try:
            certifications = self.resume_object.certifications
            if not certifications:
                logger.warning("⚠️ Inga certifikat hittade, använder fallback")
                return self._get_fallback_skills()
            
            html_parts = []
            for cert in certifications:
                name = getattr(cert, 'name', '')
                if name:
                    # Översätt till engelska om nödvändigt
                    if self.language == 'en':
                        name = self._translate_skill_to_english(name)
                    html_parts.append(f'<div class="knowledge-item">• {name}</div>')
            
            logger.info(f"✅ Kunskaper genererade: {len(html_parts)} poster")
            return '\n            '.join(html_parts)
            
        except Exception as e:
            logger.error(f"❌ Fel vid kunskaper: {e}")
            return self._get_fallback_skills()
    
    def _translate_skill_to_english(self, skill: str) -> str:
        """Översätt färdighet till engelska"""
        translations = {
            'Programmering i Python': 'Programming in Python',
            'Programmering i C#': 'Programming in C#',
            'Programmering i Java': 'Programming in Java',
            'Databas teknik i SQL': 'Database Technology in SQL',
            'Extra kurs inom Webbdesign I & II': 'Extra Course in Web Design I & II',
            'Webbutveckling I & II': 'Web Development I & II',
            'B-Körkort': "B Driver's License"
        }
        return translations.get(skill, skill)
    
    def _get_fallback_skills(self) -> str:
        """Fallback kunskaper"""
        if self.language == 'en':
            return '''<div class="knowledge-item">• Programming in Python</div>
            <div class="knowledge-item">• Programming in C#</div>
            <div class="knowledge-item">• Programming in Java</div>
            <div class="knowledge-item">• Database Technology in SQL</div>
            <div class="knowledge-item">• Extra Course in Web Design I & II</div>
            <div class="knowledge-item">• Microsoft Windows, Linux</div>
            <div class="knowledge-item">• B Driver's License</div>'''
        else:
            return '''<div class="knowledge-item">• Programmering i Python</div>
            <div class="knowledge-item">• Programmering i C#</div>
            <div class="knowledge-item">• Programmering i Java</div>
            <div class="knowledge-item">• Databas teknik i SQL</div>
            <div class="knowledge-item">• Extra kurs inom Webbdesign I & II</div>
            <div class="knowledge-item">• Microsoft Windows, Linux</div>
            <div class="knowledge-item">• B-Körkort</div>'''
    
    def _generate_languages_section(self) -> str:
        """Genererar språk från RIKTIG data"""
        try:
            languages = self.resume_object.languages
            if not languages:
                logger.warning("⚠️ Inga språk hittade, använder fallback")
                return self._get_fallback_languages()
            
            html_parts = []
            for lang in languages:
                language_name = getattr(lang, 'language', 'Språk')
                proficiency = getattr(lang, 'proficiency', '')
                
                # Översätt till engelska om nödvändigt
                if self.language == 'en':
                    language_name = self._translate_language_name(language_name)
                    proficiency = self._translate_proficiency(proficiency)
                
                html_parts.append(f'<div class="language-item">• {language_name} ({proficiency})</div>')
            
            logger.info(f"✅ Språk genererade: {len(html_parts)} poster")
            return '\n            '.join(html_parts)
            
        except Exception as e:
            logger.error(f"❌ Fel vid språk: {e}")
            return self._get_fallback_languages()
    
    def _translate_language_name(self, lang: str) -> str:
        """Översätt språknamn"""
        translations = {
            'Svenska': 'Swedish',
            'Engelska': 'English',
            'Spanska': 'Spanish'
        }
        return translations.get(lang, lang)
    
    def _translate_proficiency(self, prof: str) -> str:
        """Översätt språknivå"""
        translations = {
            'Modersmål': 'Native Language',
            'Flytande': 'Fluent',
            'God': 'Good',
            'Grundläggande': 'Basic'
        }
        return translations.get(prof, prof)
    
    def _get_fallback_languages(self) -> str:
        """Fallback språk"""
        if self.language == 'en':
            return '''<div class="language-item">• Swedish (Native Language)</div>
            <div class="language-item">• English (Fluent)</div>
            <div class="language-item">• Spanish (Native Language)</div>'''
        else:
            return '''<div class="language-item">• Svenska (Modersmål)</div>
            <div class="language-item">• Engelska (Flytande)</div>
            <div class="language-item">• Spanska (Modersmål)</div>'''
    
    def _generate_contact_section(self) -> str:
        """Genererar kontakt från RIKTIG data"""
        try:
            personal_info = self.resume_object.personal_information
            if not personal_info:
                logger.warning("⚠️ Ingen kontaktinfo hittad, använder fallback")
                return self._get_fallback_contact()
            
            email = getattr(personal_info, 'email', '')
            phone = getattr(personal_info, 'phone', '')
            address = getattr(personal_info, 'address', '')
            city = getattr(personal_info, 'city', '')
            website = getattr(personal_info, 'website', '')
            
            # Formatera adress
            full_address = f"{address}, {city}"
            
            contact_html = f'''<div class="contact-item">
                <span class="icon">📧</span>{email}
            </div>
            <div class="contact-item">
                <span class="icon">📱</span>{phone}
            </div>
            <div class="contact-item">
                <span class="icon">📍</span>{full_address}
            </div>
            <div class="contact-item">
                <span class="icon">🌐</span>{website}
            </div>'''
            
            logger.info(f"✅ Kontakt genererad: {email}")
            return contact_html
            
        except Exception as e:
            logger.error(f"❌ Fel vid kontakt: {e}")
            return self._get_fallback_contact()
    
    def _get_fallback_contact(self) -> str:
        """Fallback kontakt"""
        return '''<div class="contact-item">
            <span class="icon">📧</span>email@example.com
        </div>
        <div class="contact-item">
            <span class="icon">📱</span>070-000 00 00
        </div>
        <div class="contact-item">
            <span class="icon">📍</span>Stad, Sverige
        </div>'''
    
    def _generate_experience_section(self, job_description: str) -> str:
        """
        Genererar erfarenhetssektion med AI-anpassning
        Läser från RIKTIG data och anpassar till jobbeskrivning
        """
        try:
            experience_details = self.resume_object.experience_details
            if not experience_details:
                logger.warning("⚠️ Ingen erfarenhet hittad, använder fallback")
                return self._get_fallback_experience()

            # ✅ INKLUDERA ALLA ERFARENHETER - AI:n väljer vad som är relevant för jobbet
            # Tidigare filtrerade vi bort Undersköterska vilket tog bort ERCP-assistent (viktig current job!)
            all_experiences = experience_details

            # Filtrera bort LLM-felmeddelanden som jobbbeskrivning
            _error_patterns = ["i'm sorry", "i cannot", "cannot provide", "not included in", "no job description", "please verify", "are you a robot"]
            is_valid_description = job_description and len(job_description.strip()) > 100 and not any(p in job_description.lower() for p in _error_patterns)

            # Om AI finns och giltig jobbeskrivning ges, anpassa innehållet
            if self.llm and is_valid_description:
                logger.info("🤖 Använder AI för att anpassa ALLA erfarenheter till jobbeskrivning")
                return self._ai_adapt_experiences(all_experiences, job_description)
            else:
                if not is_valid_description:
                    logger.warning("⚠️ Ingen giltig jobbeskrivning tillgänglig - genererar standarderfarenheter")
                logger.info("📄 Genererar ALLA standarderfarenheter (ingen AI-anpassning)")
                return self._format_experiences_standard(all_experiences)
                
        except Exception as e:
            logger.error(f"❌ Fel vid erfarenhet: {e}")
            return self._get_fallback_experience()
    
    def _ai_adapt_experiences(self, experiences: List, job_description: str) -> str:
        """Använder AI för att anpassa erfarenheter till jobbeskrivning (max 25%)"""
        try:
            # Bygg prompt för AI
            experiences_text = self._format_experiences_for_ai(experiences)

            prompt = f"""You are a professional CV optimizer. You may adapt up to 25% of the text to match the job, but keep 75% EXACTLY as written.

Job Description:
{job_description[:2000]}

Current Experiences:
{experiences_text}


CRITICAL RULES:

1. KEEP 75% OF TEXT EXACTLY AS WRITTEN - Only adapt up to 25%
2. ALL text MUST be in {"Swedish" if self.language == 'sv' else "English"} - NO mixed languages
3. Translate job titles to {"Swedish" if self.language == 'sv' else "English"}
4. Read the job description and rephrase bullet points to emphasize skills that match (max 25% change)
5. NEVER lie or add skills that weren't mentioned in the original
6. Keep the ESSENCE of each job exactly as it was

WHAT YOU CAN DO (25% adaptation):
- Reorder bullet points (most relevant first for this job)
- Rephrase to emphasize aspects that match the job description
- Translate job titles consistently
- Adjust wording to mirror keywords from the job description where truthful

WHAT YOU CANNOT DO:
- Change the job type (healthcare stays healthcare, construction stays construction)
- Add technologies or skills not mentioned in the original
- Remove important details
- Exceed 25% changes

LANGUAGE RULE:
- If language is Swedish: ALL text in Swedish (translate English terms to Swedish context)
- If language is English: ALL text in English (translate Swedish terms to English)
- NEVER mix Swedish and English in same document

EXAMPLE (Swedish job):

ORIGINAL (mixed language):
"Assistent vid avancerade endoskopiska ingrepp"
"Worked with React and JavaScript"

CORRECT (all Swedish):
• Assistent vid avancerade endoskopiska ingrepp för diagnostik och behandling
• Arbetade med React och JavaScript i egen verksamhet

WRONG (mixed):
• Assistent vid avancerade endoskopiska ingrepp
• Worked with React and JavaScript

Format:
<div class="experience-item">
    <div class="experience-title">Position at Company Name</div>
    <div class="experience-company">2020 - Present</div>
    <div class="experience-description">
        • [Bullet 1 - 85-100% original text]<br>
        • [Bullet 2 - 85-100% original text]<br>
    </div>
</div>

Return ONLY the HTML in {"Swedish" if self.language == 'sv' else "English"}.
"""
            
            # Anropa AI
            ai_response = self.llm.invoke(prompt)
            
            if ai_response and '<div class="experience-item">' in ai_response:
                logger.info("✅ AI-anpassade erfarenheter genererade")
                # Rensa bort markdown-syntax som AI kan ha lagt till
                cleaned_response = ai_response.replace('```html', '').replace('```', '').strip()
                return cleaned_response
            else:
                logger.warning("⚠️ AI-svar var inte i rätt format, använder standard")
                return self._format_experiences_standard(experiences)
                
        except Exception as e:
            logger.error(f"❌ AI-anpassning misslyckades: {e}")
            return self._format_experiences_standard(experiences)
    
    def _format_experiences_for_ai(self, experiences: List) -> str:
        """Formaterar erfarenheter för AI-prompt"""
        text_parts = []
        for exp in experiences:
            position = getattr(exp, 'position', 'Position')
            company = getattr(exp, 'company', 'Company')
            period = getattr(exp, 'employment_period', '2020 - Present')
            
            responsibilities = getattr(exp, 'key_responsibilities', [])
            resp_texts = []
            for r in responsibilities:
                if isinstance(r, dict):
                    resp_texts.append(r.get('responsibility', ''))
                elif hasattr(r, 'responsibility'):
                    resp_texts.append(getattr(r, 'responsibility', ''))
                else:
                    resp_texts.append(str(r) if r else '')
            
            text_parts.append(f"{position} at {company} ({period})")
            text_parts.extend([f"- {r}" for r in resp_texts[:5]])  # Max 5 bullet points
            text_parts.append("")
        
        return "\n".join(text_parts)
    
    def _format_experiences_standard(self, experiences: List) -> str:
        """Formaterar erfarenheter utan AI-anpassning"""
        html_parts = []
        
        for exp in experiences:
            position = getattr(exp, 'position', 'Position')
            company = getattr(exp, 'company', 'Company')
            period = getattr(exp, 'employment_period', '2020 - Present')
            
            # Översätt om engelska
            if self.language == 'en':
                position = self._translate_position_to_english(position)
                period = period.replace('Nuvarande', 'Current').replace('Present', 'Current')
            
            # Hämta responsibilities
            responsibilities = getattr(exp, 'key_responsibilities', [])
            resp_html_parts = []

            for resp in responsibilities[:4]:  # Max 4 bullet points
                if isinstance(resp, dict):
                    resp_text = resp.get('responsibility', '')
                elif hasattr(resp, 'responsibility'):
                    resp_text = getattr(resp, 'responsibility', '')
                else:
                    resp_text = str(resp) if resp else ''

                if resp_text:
                    resp_html_parts.append(f"• {resp_text}<br>")
            
            resp_html = "\n                    ".join(resp_html_parts)

            # Translate company name if needed
            if self.language == 'en' and company == "Egen verksamhet":
                company = "Self-employed"

            # Format title to include company name (matching old CV format)
            full_title = f"{position}"

            # Show company in the company line if it's a real company
            company_line = period
            if company and company not in ["Egen verksamhet", "Self-employed"]:
                company_line = f"{company} ({period})"
            else:
                # For self-employed, just show the period
                company_line = period

            html_parts.append(f'''<div class="experience-item">
                <div class="experience-title">{full_title}</div>
                <div class="experience-company">{company_line}</div>
                <div class="experience-description">
                    {resp_html}
                </div>
            </div>''')
        
        return '\n            '.join(html_parts)
    
    def _translate_position_to_english(self, position: str) -> str:
        """Översätt position till engelska"""
        translations = {
            'Ägare & Projektledare': 'Owner & Project Manager',
            'Dataingenjör & Systemutvecklare': 'Computer Engineer & System Developer',
            'System- & Nätverksadministratör': 'System & Network Administrator',
            'Undersköterska': 'Nursing Assistant'
        }
        return translations.get(position, position)
    
    def _get_fallback_experience(self) -> str:
        """Fallback erfarenhet"""
        if self.language == 'en':
            return '''<div class="experience-item">
                <div class="experience-title">Web Development & System Integration</div>
                <div class="experience-company">2022 - Current</div>
                <div class="experience-description">
                    • Developed and implemented fullstack web applications with modern technologies (JavaScript, HTML5, CSS3, PHP)<br>
                    • Designed and built scalable database systems with client administration interfaces<br>
                    • Completed two comprehensive courses in web development focusing on modern development methods<br>
                    • Experience with version control and collaboration through GitHub, GitLab and integration with Copilot
                </div>
            </div>
            <div class="experience-item">
                <div class="experience-title">System Development & Programming</div>
                <div class="experience-company">2021 - Current</div>
                <div class="experience-description">
                    • Practical experience with object-oriented programming in Java with completed courses and projects<br>
                    • Developed applications in C# with focus on system integration and user interfaces<br>
                    • Experience with Python programming with focus on automation and data processing<br>
                    • Ongoing development of own AI agent for personal use
                </div>
            </div>'''
        else:
            return '''<div class="experience-item">
                <div class="experience-title">Webbutveckling & Systemintegration</div>
                <div class="experience-company">2022 - Nuvarande</div>
                <div class="experience-description">
                    • Utvecklat och implementerat fullstack-webbapplikationer med moderna teknologier (JavaScript, HTML5, CSS3, PHP)<br>
                    • Designat och byggt skalbara databassystem med klientadministrationsgränssnitt<br>
                    • Genomfört två omfattande kurser inom webbutveckling med fokus på moderna utvecklingsmetoder<br>
                    • Erfarenhet av versionshantering och samarbete genom GitHub, GitLab och integration med Copilot
                </div>
            </div>
            <div class="experience-item">
                <div class="experience-title">Systemutveckling & Programmering</div>
                <div class="experience-company">2021 - Nuvarande</div>
                <div class="experience-description">
                    • Praktisk erfarenhet av objektorienterad programmering i Java med genomförda kurser och projekt<br>
                    • Utvecklat applikationer i C# med fokus på systemintegration och användargränssnitt<br>
                    • Erfarenhet av Python-programmering med inriktning mot automation och databehandling<br>
                    • Pågående utveckling av egen AI-agent för personligt bruk
                </div>
            </div>'''
    
    def _generate_technical_skills(self) -> str:
        """Genererar tekniska färdigheter från RIKTIG data"""
        try:
            # Samla alla skills från alla erfarenheter
            all_skills = set()
            experience_details = self.resume_object.experience_details
            
            if experience_details:
                for exp in experience_details:
                    skills = getattr(exp, 'skills_acquired', [])
                    for skill in skills:
                        all_skills.add(str(skill))
            
            if not all_skills:
                logger.warning("⚠️ Inga tekniska färdigheter hittade, använder fallback")
                return self._get_fallback_technical_skills()
            
            # Gruppera skills
            programming_langs = [s for s in all_skills if any(lang in s for lang in ['JavaScript', 'Python', 'Java', 'C#', 'PHP', 'HTML', 'CSS'])]
            tools = [s for s in all_skills if any(tool in s for tool in ['Git', 'GitHub', 'GitLab', 'Copilot', 'Linux', 'Windows'])]
            other = [s for s in all_skills if s not in programming_langs and s not in tools]
            
            if self.language == 'en':
                html = '<ul>\n'
                if programming_langs:
                    html += f'                <li>• Programming Languages: {", ".join(sorted(programming_langs))}</li>\n'
                if tools:
                    html += f'                <li>• Tools & Environments: {", ".join(sorted(tools))}</li>\n'
                if other:
                    html += f'                <li>• Other Skills: {", ".join(sorted(other))}</li>\n'
                html += '            </ul>'
            else:
                html = '<ul>\n'
                if programming_langs:
                    html += f'                <li>• Programmeringsspråk: {", ".join(sorted(programming_langs))}</li>\n'
                if tools:
                    html += f'                <li>• Verktyg & Miljöer: {", ".join(sorted(tools))}</li>\n'
                if other:
                    html += f'                <li>• Övriga färdigheter: {", ".join(sorted(other))}</li>\n'
                html += '            </ul>'
            
            logger.info(f"✅ Tekniska färdigheter genererade: {len(all_skills)} skills")
            return html
            
        except Exception as e:
            logger.error(f"❌ Fel vid tekniska färdigheter: {e}")
            return self._get_fallback_technical_skills()
    
    def _get_fallback_technical_skills(self) -> str:
        """Fallback tekniska färdigheter"""
        if self.language == 'en':
            return '''<ul>
                <li>• Programming Languages: JavaScript, HTML5, CSS3, PHP, Java, Python, C#</li>
                <li>• Tools & Environments: Git, GitHub, GitLab, Copilot, Linux, Windows</li>
                <li>• Databases & Systems: SQL, Relational Databases, Virtualization</li>
                <li>• Network & Security: Network Protocols, Security Implementation, System Monitoring</li>
                <li>• Mathematics: Single Variable Analysis, Logical Thinking, Problem Solving</li>
            </ul>'''
        else:
            return '''<ul>
                <li>• Programmeringsspråk: JavaScript, HTML5, CSS3, PHP, Java, Python, C#</li>
                <li>• Verktyg & Miljöer: Git, GitHub, GitLab, Copilot, Linux, Windows</li>
                <li>• Databaser & System: SQL, Relationsdatabaser, Virtualisering</li>
                <li>• Nätverk & Säkerhet: Nätverksprotokoll, Säkerhetsimplementation, Systemövervakning</li>
                <li>• Matematik: Envariabelanalys, Logiskt tänkande, Problemlösning</li>
            </ul>'''
    
    def generate_complete_cv_html(
        self,
        job_description: Optional[str] = None,
        job_description_for_language: Optional[str] = None
    ) -> str:
        """
        Genererar komplett CV HTML enligt exakt design från bilden

        Args:
            job_description: Sammanfattad jobbeskrivning för CV-innehåll
            job_description_for_language: FULL jobbeskrivning för språkdetektering (om tillgänglig)
        """
        try:
            # ALLTID SVENSKA - CV ska alltid vara på svenska för svenska jobbanvändare
            # (Samma logik som cover_letter_generator.py)
            self.language = 'sv'
            logger.info("🇸🇪 CV: ALLTID SVENSKA (hardcoded)")

            logger.info(f"🎨 Genererar KOMPLETT CV på {self.language} med RIKTIG data från resume_object")
            
            # Generera alla sektioner från RIKTIG data
            education_html = self._generate_education_section()
            skills_html = self._generate_skills_section()
            languages_html = self._generate_languages_section()
            contact_html = self._generate_contact_section()
            experience_html = self._generate_experience_section(job_description or "")
            technical_skills_html = self._generate_technical_skills()
            
            # Personlig information
            full_name, job_title, summary = self._generate_personal_info()
            
            # Profilbild
            profile_image_base64 = self._get_profile_image_base64()
            
            # Ladda template — router baserat på CV_DESIGN env
            import os
            CV_TEMPLATE_MAP = {
                'design_02_classic':      'improved_template.html',
                'design_03_modern_green': 'template_modern_green.html',
                'design_07_tech_modern':  'template_tech_modern.html',
            }
            chosen = os.getenv('CV_DESIGN', 'design_02_classic')
            template_filename = CV_TEMPLATE_MAP.get(chosen, 'improved_template.html')
            template_path = Path(__file__).parent / template_filename
            if not template_path.exists():
                logger.warning(f'CV template "{template_filename}" saknas, fallback till improved_template.html')
                template_path = Path(__file__).parent / "improved_template.html"
            logger.info(f'Använder CV-template: {template_path.name} (CV_DESIGN={chosen})')
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # Ersätt placeholders
            from string import Template
            template_obj = Template(template)
            
            translations = self._get_translations()[self.language]
            
            complete_html = template_obj.substitute(
                profile_image=profile_image_base64,
                education_title=translations['education_title'],
                education_content=education_html,
                skills_title=translations['skills_title'],
                skills_content=skills_html,
                languages_title=translations['languages_title'],
                languages_content=languages_html,
                contact_title=translations['contact_title'],
                contact_content=contact_html,
                full_name=full_name,
                job_title=job_title,
                summary=summary,
                experience_title=translations['experience_title'],
                experience_content=experience_html,
                technical_skills_title=translations['technical_skills_title'],
                technical_skills=technical_skills_html,
                download_text=translations['download_text']
            )
            
            logger.info(f"✅ KOMPLETT CV genererat på {self.language} ({len(complete_html)} tecken)")
            logger.info("🎉 ALLA SEKTIONER INKLUDERADE: Profilbild, Utbildning, Kunskaper, Språk, Kontakt, Erfarenhet, Tekniska färdigheter")
            
            return complete_html
            
        except Exception as e:
            logger.error(f"❌ Fel vid CV-generering: {e}")
            raise
