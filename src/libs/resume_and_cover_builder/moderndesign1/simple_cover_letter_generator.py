"""
ENKEL Cover Letter Generator - Följer Victors referensbrev exakt
Ingen fancy formattering - bara det personliga brevet
"""

from pathlib import Path
from typing import Any
from loguru import logger
from .isolated_utils import create_isolated_llm


class SimpleCoverLetterGenerator:
    """
    Genererar personliga brev baserat EXAKT på Victors referensbrev
    Minimal AI-anpassning - behåller originalets stil och ton
    """

    def __init__(self, resume_object: Any, api_key: str):
        self.resume_object = resume_object
        self.api_key = api_key
        self.llm = create_isolated_llm(api_key) if api_key else None
        logger.info("📧 SimpleCoverLetterGenerator initialiserad")

    def _load_reference_cover_letter(self) -> str:
        """Laddar referens personligt brev"""
        try:
            ref_path = Path("data_folder/reference_cover_letter.pdf")
            txt_path = Path("data_folder/REFERENCES_GUIDE.txt")

            # Använd cover_letter_profile från YAML som innehåller referenstexten
            cover_profile = getattr(self.resume_object, 'cover_letter_profile', '')
            if cover_profile:
                logger.info("✅ Använder cover_letter_profile från YAML")
                return cover_profile

            logger.warning("⚠️ Ingen cover_letter_profile hittad")
            return self._get_default_letter()

        except Exception as e:
            logger.error(f"❌ Fel vid laddning av referens: {e}")
            return self._get_default_letter()

    def _get_default_letter(self) -> str:
        """Standard personligt brev om inget annat finns"""
        return """Hej!

Jag är en nyfiken systemutvecklare med ett stort intresse för teknik. Jag gillar att förstå hur system fungerar och att hitta lösningar på tekniska utmaningar.

Min bakgrund består av dataingenjörsutbildning vid Gävle högskola, kompletterat med kurser på olika universitet för att vidga mina perspektiv inom området. Även om jag inte har formell arbetslivserfarenhet som systemutvecklare har jag byggt upp mycket praktisk erfarenhet genom egenutvecklade projekt. Jag har arbetat med att utveckla webbapplikationer, automatiseringsagenter och säkerhetssystem för pentesting. På senaste tiden har jag särskilt fokuserat på att utforska AI och automatiseringsverktyg, vilket har öppnat nya intressanta områden att fördjupa mig i.

Jag skulle beskriva mig som någon som befinner sig på en solid mellannivå – varken nybörjare men heller inte specialist inom något specifikt område. Jag har breda grundkunskaper inom flera tekniska områden och en stor nyfikenhet att lära mig mer. Jag värdesätter att arbeta i team där kunskapsutbyte och samarbete står i fokus, eftersom jag tror att man utvecklas bäst när man får både ge och ta i form av kunskap.

Jag är van att arbeta både självständigt och i samarbete med andra. Jag tar ansvar för mina uppgifter och ser kommunikation som en viktig del i att nå goda resultat. Min drivkraft handlar om kontinuerlig utveckling och att hela tiden lära mig nya saker.

Jag kan gärna dela med mig av mina projekt och tillhandahålla referenser på begäran.

Med vänliga hälsningar,
[Ditt namn]"""

    def generate_simple_cover_letter(
        self,
        job_description: str = "",
        company_name: str = "",
        position_title: str = "",
        language: str = 'sv'
    ) -> str:
        """
        Genererar ett enkelt personligt brev

        VIKTIGT: Använder referensbrevet som bas med MINIMAL anpassning
        """
        # Normalisera språkkod: 'svenska' -> 'sv', 'engelska' -> 'en'
        if language == 'svenska':
            language = 'sv'
        elif language == 'engelska':
            language = 'en'

        logger.info(f"📝 Genererar enkelt personligt brev för {company_name} - {position_title} (språk: {language})")

        # Ladda referensbrevet
        reference_letter = self._load_reference_cover_letter()

        # Om vi inte har någon jobbinformation, använd referensen direkt
        if not job_description or not company_name:
            logger.info("✅ Använder referensbrev utan anpassning (ingen jobbinfo)")
            return self._format_simple_letter(reference_letter, language)

        # Om vi har jobbinformation, gör MINIMAL anpassning
        if self.llm and job_description:
            try:
                adapted_letter = self._minimal_adaptation(
                    reference_letter,
                    job_description,
                    company_name,
                    position_title,
                    language
                )
                return self._format_simple_letter(adapted_letter, language)
            except Exception as e:
                logger.error(f"❌ AI-anpassning misslyckades: {e}")
                logger.info("⚠️ Använder referensbrev utan anpassning (fallback)")
                return self._format_simple_letter(reference_letter, language)

        # Fallback: använd referensen direkt
        return self._format_simple_letter(reference_letter, language)

    def _minimal_adaptation(
        self,
        reference: str,
        job_desc: str,
        company: str,
        position: str,
        language: str
    ) -> str:
        """
        Gör MYCKET minimal anpassning av referensbrevet
        Målet: Behålla 95% av originalet, lägg endast till 1-2 meningar
        """

        prompt = f"""Du är expert på att göra MINIMAL anpassning av personliga brev.

ORIGINALBREV (detta är MALLEN - behåll nästan allt):
{reference}

JOBB SOM SKA SÖKAS:
Företag: {company}
Position: {position}
Beskrivning (första 1000 tecken): {job_desc[:1000]}

UPPGIFT:
Gör MINIMAL anpassning av originalbrevet:

1. BEHÅLL 95% av originaltexten exakt som den är
2. Lägg ENDAST till 1-2 meningar om:
   - Varför just {company} är intressant
   - Hur erfarenhet matchar positionen {position}
3. Lägg till dessa meningar NATURLIGT i flödet, inte som ny paragraf
4. ÄNDRA INTE stilen, tonen eller personligheten
5. ÄNDRA INTE längden nämnvärt

Språk: {'Svenska' if language == 'sv' else 'Engelska'}

VIKTIGT:
- Detta ska INTE bli ett formellt "Dear Hiring Manager" brev
- Behåll den personliga, ödmjuka tonen
- Behåll struktur och längd
- Kopiera majoriteten av originaltexten

Returnera ENDAST brevet, ingen header."""

        try:
            adapted = self.llm(prompt).strip()
            logger.info(f"✅ Minimal anpassning klar ({len(adapted)} tecken)")
            return adapted
        except Exception as e:
            logger.error(f"❌ Anpassning misslyckades: {e}")
            return reference

    def _format_simple_letter(self, content: str, language: str) -> str:
        """
        Formaterar brevet i ENKELT textformat - INGEN HTML, INGA headers
        Exakt som referensen
        """

        # Ta bort eventuella formella headers om de råkat komma med
        content = content.replace("Dear Hiring Manager,", "")
        content = content.replace("Bästa rekryteringsteam,", "")

        # Enkel textformatering
        letter = "Personligt Brev\n\n"

        # Om brevet inte börjar med "Hej!", lägg till det
        if not content.strip().startswith("Hej"):
            letter += "Hej!\n\n"

        letter += content.strip()

        # Säkerställ att det slutar med signatur
        if "Med vänliga hälsningar" not in letter and "Sincerely" not in letter:
            if language == 'sv':
                letter += "\n\nMed vänliga hälsningar,\n[Ditt namn]"
            else:
                letter += "\n\nSincerely,\n[Your name]"

        return letter

    def generate_html_cover_letter(
        self,
        job_description: str = "",
        company_name: str = "",
        position_title: str = "",
        language: str = 'sv'
    ) -> str:
        """
        Genererar HTML-version av det enkla brevet
        Minimal styling - ser ut som text
        """
        # Normalisera språkkod: 'svenska' -> 'sv', 'engelska' -> 'en'
        if language == 'svenska':
            language = 'sv'
        elif language == 'engelska':
            language = 'en'

        text_letter = self.generate_simple_cover_letter(
            job_description, company_name, position_title, language
        )

        # Konvertera till minimal HTML
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: 'Calibri', 'Arial', sans-serif;
            font-size: 12pt;
            line-height: 1.6;
            max-width: 800px;
            margin: 40px auto;
            padding: 20px;
            color: #333;
        }}
        h1 {{
            font-size: 14pt;
            font-weight: normal;
            margin-bottom: 30px;
        }}
        p {{
            margin-bottom: 15px;
            text-align: left;
            word-spacing: normal;
            hyphens: none;
        }}
    </style>
</head>
<body>
    <pre style="font-family: 'Calibri', 'Arial', sans-serif; white-space: pre-wrap;">{text_letter}</pre>
</body>
</html>"""

        return html
