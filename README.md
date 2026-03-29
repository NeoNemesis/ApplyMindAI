# ApplyMind AI

**AI-powered job application assistant** — search Swedish job boards, score jobs against your profile, and generate tailored CVs and cover letters in minutes. Available as both a desktop app and a web interface.

---

## Features

- **Desktop app** — native window via pywebview + system tray icon (pystray)
- **Web interface** — full Flask dashboard accessible in any browser
- **Multi-platform job search** — Indeed, Arbetsförmedlingen, Jobtech API
- **ATS scoring** — AI rates each job's match against your profile before generating documents
- **AI-tailored documents** — GPT-4o rewrites your CV and cover letter per job description
- **Dual design system** — Modern Design 1 (clean) and Modern Design 2 (bold) PDF layouts
- **Duplicate detection** — never processes the same job twice
- **Multi-language support** — output documents match the language of the job posting (Swedish/English)
- **Job tracker** — Kanban-style board to track application status
- **Letter templates** — reusable cover letter templates per industry/role
- **Email notifications** — optional alerts when new jobs are found

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10+ |
| Google Chrome | Latest |
| OpenAI API key | Any tier (GPT-4o) |

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/NeoNemesis/JobpowercraftAI.git
cd JobpowercraftAI
```

### 2. Create and activate a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure your profile

```bash
# Copy example files
cp data_folder_example/secrets.yaml.example data_folder/secrets.yaml
cp data_folder_example/job_scraper_config.yaml data_folder/job_scraper_config.yaml
```

Edit `data_folder/secrets.yaml` and add your OpenAI API key:

```yaml
openai_api_key: "sk-..."
```

Edit `data_folder/job_scraper_config.yaml` with your job search preferences.

### 5. Launch

**Desktop app (recommended):**
```bash
pythonw ApplyMindAI.pyw
```

**Web interface only:**
```bash
python web_app.py
# Then open http://localhost:5000
```

---

## Project Structure

```
ApplyMind AI/
├── ApplyMindAI.pyw              # Desktop app entry point (pywebview + pystray)
├── web_app.py                   # Flask web server
├── job_master.py                # Core job search orchestration
├── config.py                    # App configuration
├── requirements.txt
│
├── templates/                   # Jinja2 HTML templates
│   ├── index.html               # Dashboard
│   ├── jobs.html                # Job list + ATS scores
│   ├── tracker.html             # Kanban tracker
│   ├── search.html              # Search configuration
│   ├── settings.html            # Profile & API settings
│   └── ...
│
├── static/                      # CSS, JS, assets
│
├── src/
│   ├── job_scrapers.py          # Indeed / AF / Jobtech scrapers
│   ├── i18n.py                  # Swedish/English translations
│   ├── libs/
│   │   ├── llm_manager.py       # OpenAI GPT-4o integration
│   │   └── resume_and_cover_builder/
│   │       ├── moderndesign1/   # Clean PDF layout
│   │       └── moderndesign2/   # Bold PDF layout
│   └── utils/
│
└── data_folder/
    ├── plain_text_resume.yaml   # Your resume content (not committed)
    ├── secrets.yaml             # API keys (not committed)
    └── output/                  # Generated CVs and cover letters
```

---

## Output

Generated documents are saved to `data_folder/output/`:

```
data_folder/output/
└── [Company] - [Job Title]/
    ├── CV_[Name]_[Company].pdf
    └── CoverLetter_[Name]_[Company].pdf
```

---

## Tech Stack

- **Backend:** Python · Flask · OpenAI GPT-4o
- **Frontend:** HTML · CSS · JavaScript · Jinja2
- **Desktop:** pywebview · pystray
- **PDF generation:** ReportLab · WeasyPrint
- **Scraping:** Selenium · BeautifulSoup · Playwright
- **APIs:** Jobtech (Arbetsförmedlingen)

---

## Security

Sensitive files are excluded from version control via `.gitignore`:

- `data_folder/secrets.yaml` — API keys
- `data_folder/plain_text_resume.yaml` — personal resume data
- `data_folder/output/` — generated documents
- `.env` — environment variables

---

## License

MIT
