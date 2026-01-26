FROM python:3.9-slim

# Playwright اور اس کی dependencies کے لیے ضروری ٹولز
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright کے براؤزرز انسٹال کرو
RUN playwright install chromium
RUN playwright install-deps

COPY . .

# Flask پورٹ
EXPOSE 5000

CMD ["python", "app.py"]
