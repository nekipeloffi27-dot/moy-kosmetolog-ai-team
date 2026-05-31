FROM python:3.12-slim

WORKDIR /app

# System deps: build tools + playwright/chromium runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates \
        # Chromium runtime libs (for playwright)
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
        libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxext6 \
        libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        fonts-liberation libappindicator3-1 libnss3-tools \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install chromium for playwright (~150 MB)
RUN python -m playwright install chromium

CMD ["python", "-m", "bot.main"]
