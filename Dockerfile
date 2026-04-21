FROM python:3.11-slim

WORKDIR /app

# تثبيت مكتبات النظام المطلوبة (cairo, pango, gdk-pixbuf...)
RUN apt-get update && apt-get install -y \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi8 \
    libgobject-2.0-0 \
    libharfbuzz0b \
    fontconfig \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# تثبيت مكتبات Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ ملفات المشروع
COPY . .

CMD ["python3", "bot.py"]
