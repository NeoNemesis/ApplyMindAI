FROM python:3.11-slim

WORKDIR /app

# System dependencies + Playwright browser deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpangocairo-1.0-0 libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.production.txt .
RUN pip install --no-cache-dir -r requirements.production.txt

# Installera Playwright Chromium (headless, ingen X11 behövs)
RUN playwright install chromium --with-deps 2>/dev/null || playwright install chromium

# App source
COPY . .

# Create instance directory
RUN mkdir -p instance/uploads

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "web_app:app"]
