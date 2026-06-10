"""
Cover Letter Generator för Modern Design 1
✅ Genererar professionella personliga brev
✅ AI-anpassning till jobbeskrivning
✅ Samma design-språk som CV:et
"""

from pathlib import Path
from typing import Any, Optional
from datetime import datetime
from loguru import logger
from .language_detector import detect_job_language
from .isolated_utils import create_isolated_llm, image_to_base64

class ModernDesign1CoverLetterGenerator:
    """
    Generator för personliga brev med Modern Design 1 stil
    """
    
    def __init__(self, resume_object: Any, api_key: str, data_dir: Optional[Path] = None):
        self.resume_object = resume_object
        self.api_key = api_key
        # Per-user datakatalog (referensbrev m.m.). None = desktop-läge.
        self.data_dir = Path(data_dir) if data_dir else None
        self.language = 'sv'
        try:
            self.llm = create_isolated_llm(api_key)
        except Exception as e:
            logger.warning(f"⚠️ Ingen LLM tillgänglig — kör utan AI-anpassning: {e}")
            self.llm = None
        logger.info("📧 ModernDesign1CoverLetterGenerator initialiserad")
    
    def _get_profile_image_base64(self) -> str:
        """CLEAN VERSION: Ingen profilbild i personliga brev"""
        # Clean version använder INTE profilbild - mer professionellt
        return ""
    
    def _get_translations(self) -> dict:
        """Översättningar för olika språk - CLEAN VERSION"""
        return {
            'sv': {
                'recipient_title': 'Rekryteringsteam',
                'job_application': 'Ansökan:',
                'salutation': 'Bästa rekryteringsteam,',
                'closing': 'Med vänlig hälsning,',
                'attachment': 'Bilaga: Curriculum Vitae'
            },
            'en': {
                'recipient_title': 'Recruitment Team',
                'job_application': 'Application for:',
                'salutation': 'Dear Hiring Manager,',
                'closing': 'Sincerely,',
                'attachment': 'Attached: Curriculum Vitae'
            }
        }
    
    def _generate_personal_info(self) -> tuple:
        """Hämtar personlig information"""
        try:
            personal_info = self.resume_object.personal_information
            if not personal_info:
                return self._get_fallback_personal_info()
            
            name = getattr(personal_info, 'name', '')
            surname = getattr(personal_info, 'surname', '')
            full_name = f"{name} {surname}".strip()

            email = getattr(personal_info, 'email', '')
            phone = getattr(personal_info, 'phone', '')
            address = getattr(personal_info, 'address', '')
            city = getattr(personal_info, 'city', '')
            zip_code = getattr(personal_info, 'zip_code', '')
            country = getattr(personal_info, 'country', '')
            website = getattr(personal_info, 'website', '')

            # Formatera kontaktinfo - CLEAN VERSION (inline, inga emojis)
            contact_parts = []
            if email:
                contact_parts.append(f'<div>{email}</div>')
            if phone:
                contact_parts.append(f'<div>{phone}</div>')
            if address or city:
                contact_parts.append(f'<div>{address}, {zip_code} {city}</div>'.strip(', '))
            if website:
                contact_parts.append(f'<div>{website}</div>')

            contact_html = '\n                    '.join(contact_parts)
            
            return full_name, contact_html
            
        except Exception as e:
            logger.error(f"❌ Fel vid personlig info: {e}")
            return self._get_fallback_personal_info()
    
    def _get_fallback_personal_info(self) -> tuple:
        """Fallback personlig info — tomt, aldrig påhittade/andras uppgifter"""
        return "", ""

    def _derive_job_title(self) -> str:
        """Titel från användarens senaste position i CV-datat — aldrig hårdkodad"""
        try:
            exp = getattr(self.resume_object, 'experience_details', None) or []
            pos = getattr(exp[0], 'position', '') if exp else ''
            return str(pos) if pos else ''
        except Exception:
            return ''

    def _format_text_to_paragraphs(self, text: str) -> str:
        """Formaterar text till HTML-paragrafer - CLEAN VERSION"""
        if not text:
            return ""

        # Dela upp texten på dubbla radbrytningar (paragrafer)
        paragraphs = text.strip().split('\n\n')

        # Skapa HTML-paragrafer
        html_paragraphs = []
        for para in paragraphs:
            # Ta bort enstaka radbrytningar och extra mellanslag
            cleaned_para = ' '.join(para.split())
            if cleaned_para:  # Skippa tomma paragrafer
                html_paragraphs.append(f'<p>{cleaned_para}</p>')

        return '\n'.join(html_paragraphs)
    
    def _load_reference_cover_letter(self) -> str:
        """Laddar referens personligt brev för AI-guidning.

        Med data_dir satt läses ENBART användarens eget referensbrev —
        aldrig den delade data_folder (annars guidas AI:n av admins brev)."""
        try:
            base = self.data_dir if self.data_dir else Path("data_folder")
            ref_path = base / "reference_cover_letter.txt"
            if ref_path.exists():
                with open(ref_path, 'r', encoding='utf-8') as f:
                    return f.read()
            return ""
        except Exception as e:
            logger.warning(f"⚠️ Kunde inte läsa referens brev: {e}")
            return ""
    
    def _is_invalid_ai_response(self, text: str) -> bool:
        """
        Kontrollerar om AI-svaret är ett felmeddelande eller engelska meta-kommentarer
        istället för ett korrekt personligt brev på svenska.
        """
        if not text or len(text) < 50:
            return True

        # Engelska nyckelfraser som indikerar att AI returnerade ett felmeddelande
        english_error_phrases = [
            "the company's name is not",
            "is not explicitly mentioned",
            "the provided context",
            "i cannot provide",
            "does not contain",
            "it appears to be an error",
            "no specific job description",
            "cannot determine",
            "not mentioned in",
        ]
        text_lower = text.lower()
        for phrase in english_error_phrases:
            if phrase in text_lower:
                return True

        # Om mer än 40% av meningarna är engelska (innehåller engelska ord utan svenska tecken)
        sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 20]
        if not sentences:
            return True
        english_count = sum(1 for s in sentences if not any(c in s for c in 'åäöÅÄÖ'))
        if len(sentences) > 0 and english_count / len(sentences) > 0.4:
            return True

        return False

    def _ai_generate_cover_letter_content(self, job_description: str, company_name: str, position_title: str) -> dict:
        """
        AI-ANPASSAR personligt brev baserat på cover_letter_profile som GRUND/MALL
        MAX 25% ANPASSNING - resten ska vara identiskt med original
        """
        try:
            # Hämta cover_letter_profile som grund
            cover_letter_profile = getattr(self.resume_object, 'cover_letter_profile', '')

            if not self.llm:
                logger.warning("⚠️ Ingen LLM tillgänglig, använder cover_letter_profile direkt")
                text = cover_letter_profile.strip() if cover_letter_profile else self._get_fallback_content(company_name, position_title)["section1"]
                formatted_text = self._format_text_to_paragraphs(text)
                return {
                    "section1": formatted_text,
                    "section2": "",
                    "section3": ""
                }

            if cover_letter_profile:
                logger.info("🤖 AI-anpassar personligt brev (MAX 25% ändring från din mall)")

                # Skapa AI-prompt som använder profilen som grund med MAX 25% ändringar
                prompt = f"""You are an expert at adapting cover letters while preserving the original voice.

USER'S ORIGINAL COVER LETTER (this is the BASE - keep 75% of it EXACTLY as written):
{cover_letter_profile}

JOB DETAILS:
Company: {company_name}
Position: {position_title}

JOB DESCRIPTION (use this to understand what skills and experience to emphasize):
{job_description[:1500] if job_description else 'Not available'}

TASK:
Adapt this cover letter for this specific job with MAXIMUM 25% changes.
Read the job description carefully and adjust the letter to highlight relevant skills and experience
that match what the employer is looking for. Do NOT invent skills or experience not in the original.

CRITICAL RULES:
1. KEEP 75% of the original text EXACTLY as written - only adapt up to 25%
2. Preserve the user's authentic voice, style and personality
3. Use the job description to identify which parts of the original letter to emphasize or adjust
4. Be SUBTLE about the company and position. Reference them at most ONCE in the entire letter, briefly and naturally (e.g. "rollen hos er" or a short phrase). NEVER write out the full company name + full job title together (avoid phrases like "att arbeta som [Full Position Title] på [Full Company Name]"). NEVER end the letter with a grand "möjligheten att arbeta som..." sentence.
5. Do NOT mention or imply that the candidate owns a company, runs a business, is an entrepreneur, owns "aktiebolag", is "ägare", "CTO of their own company" or similar. Keep the framing strictly as an employed/freelance developer.
6. DO NOT make the text more formal or add flowery language
7. DO NOT write about skills or experience not present in the original letter
8. Keep the same simple, honest and direct tone as the original
9. Write ALWAYS in SWEDISH (language: sv) - NEVER use English
10. Return ONLY the adapted letter body - NO salutation ("Hej!"), NO closing ("Med vänliga hälsningar")
11. Use double line breaks (\\n\\n) to separate paragraphs
12. NO error messages, NO job descriptions, JUST the adapted text

ADAPTED COVER LETTER BODY (plain text with \\n\\n between paragraphs):"""

                try:
                    # IsolatedLLM returnerar redan en sträng
                    adapted_content = self.llm(prompt).strip()

                    # Validera att AI-svaret inte är ett felmeddelande eller engelska meta-kommentarer
                    if self._is_invalid_ai_response(adapted_content):
                        logger.warning("⚠️ AI returnerade ogiltigt svar (engelska/felmeddelande), använder original")
                        adapted_content = cover_letter_profile.strip()

                    logger.info(f"✅ AI-anpassat personligt brev genererat ({len(adapted_content)} tecken)")

                    # Formatera till HTML-paragrafer
                    formatted_content = self._format_text_to_paragraphs(adapted_content)

                    return {
                        "section1": formatted_content,
                        "section2": "",
                        "section3": ""
                    }

                except Exception as e:
                    logger.error(f"❌ AI-anpassning misslyckades: {e}")
                    logger.warning("⚠️ Använder original cover_letter_profile som fallback")
                    formatted_fallback = self._format_text_to_paragraphs(cover_letter_profile.strip())
                    return {
                        "section1": formatted_fallback,
                        "section2": "",
                        "section3": ""
                    }
            else:
                logger.warning("⚠️ Ingen cover_letter_profile hittad i YAML, använder fallback")
                return self._get_fallback_content(company_name, position_title)

        except Exception as e:
            logger.error(f"❌ Fel vid AI-generering: {e}")
            return self._get_fallback_content(company_name, position_title)
    
    def _get_fallback_content(self, company_name: str, position_title: str) -> dict:
        """Fallback innehåll — neutralt, utan påhittad bakgrund.
        Används bara när användaren saknar cover_letter_profile och AI är otillgänglig."""
        if self.language == 'en':
            text = f"""I am writing to apply for the {position_title} position at {company_name}.

Please find my CV attached, which describes my background and experience in more detail. I would welcome the opportunity to tell you more in an interview."""
        else:
            text = f"""Härmed ansöker jag om tjänsten som {position_title} hos {company_name}.

Mitt CV finns bifogat och beskriver min bakgrund och erfarenhet i detalj. Jag berättar gärna mer vid en intervju."""

        formatted_text = self._format_text_to_paragraphs(text)
        return {
            "section1": formatted_text,
            "section2": "",
            "section3": ""
        }
    
    def generate_cover_letter_html(
        self,
        job_description: str,
        company_name: str,
        position_title: str,
        company_address: str = "",
        job_description_for_language: Optional[str] = None
    ) -> str:
        """
        Genererar komplett personligt brev HTML

        Args:
            job_description: Sammanfattad jobbeskrivning för brev-innehåll
            company_name: Företagsnamn
            position_title: Position/titel
            company_address: Företagsadress (valfritt)
            job_description_for_language: FULL jobbeskrivning för språkdetektering (om tillgänglig)

        Returns:
            Komplett HTML för personligt brev
        """
        try:
            # ALLTID SVENSKA - personliga brev ska alltid vara på svenska
            self.language = 'sv'
            logger.info("🇸🇪 Personligt brev: ALLTID SVENSKA (hardcoded)")

            # Hämta översättningar
            translations = self._get_translations()[self.language]
            
            # Hämta personlig info
            full_name, contact_html = self._generate_personal_info()
            
            # Hämta profilbild
            profile_image = self._get_profile_image_base64()
            
            # Generera datum (alltid svenska)
            current_date = datetime.now()
            months_sv = ['januari', 'februari', 'mars', 'april', 'maj', 'juni',
                        'juli', 'augusti', 'september', 'oktober', 'november', 'december']
            date_str = f"{current_date.day} {months_sv[current_date.month-1]} {current_date.year}"
            
            # AI-generera innehåll
            if self.llm:
                content = self._ai_generate_cover_letter_content(job_description, company_name, position_title)
            else:
                content = self._get_fallback_content(company_name, position_title)
            
            # Ladda CLEAN template — router baserat på LETTER_TEMPLATE env
            import os
            LETTER_TEMPLATE_MAP = {
                'nordic_minimal':   'cover_letter_template_clean.html',
                'problem_solution': 'cover_letter_template_problem_solution.html',
                'modern_tech':      'cover_letter_template_modern_tech.html',
            }
            chosen_letter = os.getenv('LETTER_TEMPLATE', 'nordic_minimal')
            letter_filename = LETTER_TEMPLATE_MAP.get(chosen_letter, 'cover_letter_template_clean.html')
            template_path = Path(__file__).parent / letter_filename
            if not template_path.exists():
                logger.warning(f'Brev-template "{letter_filename}" saknas, fallback till cover_letter_template_clean.html')
                template_path = Path(__file__).parent / "cover_letter_template_clean.html"
            logger.info(f'Använder brev-template: {template_path.name} (LETTER_TEMPLATE={chosen_letter})')
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()

            # Ersätt placeholders - CLEAN VERSION (inga företagsnamn/jobbtitel-rader)
            from string import Template
            template_obj = Template(template)

            complete_html = template_obj.substitute(
                full_name=full_name,
                job_title=self._derive_job_title(),
                contact_info=contact_html,
                date=date_str,
                salutation=translations['salutation'],
                section1_content=content.get('section1', ''),
                closing_text=translations['closing'],
                attachment_text=translations['attachment']
            )
            
            logger.info(f"✅ Cover Letter genererat ({len(complete_html)} tecken)")
            return complete_html
            
        except Exception as e:
            logger.error(f"❌ Fel vid cover letter-generering: {e}")
            raise

