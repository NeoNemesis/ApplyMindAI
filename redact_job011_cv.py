"""
Tar bort foto och adress fran Job_011 CV-PDF utan att regenerera.
Krav: pip install pymupdf
Kor: python redact_job011_cv.py
"""
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("Installera PyMuPDF forst:  pip install pymupdf")

PDF_PATH = (
    Path(__file__).parent
    / "data_folder" / "output" / "job_master"
    / "Job_011_Post- och Telestyrelsen_Systemutvecklare till PTS"
    / "CV_Post- och Telestyrelsen_Systemutvecklare till PTS_design_02_classic.pdf"
)

doc = fitz.open(str(PDF_PATH))
page = doc[0]  # sida 1

# --- Hitta och ta bort foto ---
# Bilder pa sidan
images = page.get_images(full=True)
for img in images:
    xref = img[0]
    rects = page.get_image_rects(xref)
    for rect in rects:
        page.add_redact_annot(rect, fill=(1, 1, 1))
        print(f"Foto markerat for borttagning: {rect}")

# --- Hitta och ta bort adressraden ---
# "Kvarnangsgatan" ar unik for kontaktpanelen
for term in ["Kvarnängsgatan"]:
    hits = page.search_for(term)
    for rect in hits:
        expanded = fitz.Rect(rect.x0 - 20, rect.y0 - 4, rect.x1 + 60, rect.y1 + 4)
        page.add_redact_annot(expanded, fill=(1, 1, 1))
        print(f"Adress markerad: {expanded}")

# "Uppsala" forekommmer aven i utbildningssektionen — redacta BARA om Y > 600 (kontaktpanelen)
for rect in page.search_for("Uppsala"):
    if rect.y0 > 600:
        expanded = fitz.Rect(rect.x0 - 30, rect.y0 - 4, rect.x1 + 10, rect.y1 + 4)
        page.add_redact_annot(expanded, fill=(1, 1, 1))
        print(f"Uppsala (kontakt) markerad: {expanded}")
    else:
        print(f"Uppsala vid y={rect.y0:.0f} ignorerad (utbildningssektion)")

page.apply_redactions()

# Spara som ny fil
out_path = PDF_PATH.parent / "CV_PTS_Systemutvecklare_ingen_foto_adress.pdf"
doc.save(str(out_path))
doc.close()

print(f"\nSparad: {out_path.name}")
print("Oppna filen och verifiera att foto och adress ar borttagna.")
