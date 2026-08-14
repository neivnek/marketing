FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy fonts to system directory so FFmpeg can find them globally
COPY assets/fonts/ /usr/share/fonts/khmer/
RUN fc-cache -f -v

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browser + OS libs — bắt buộc cho mode `auto` (Meta Ads scraper)
# và AI B-roll (Google Labs client). Thiếu bước này 2 mode đó sẽ lỗi
# "Executable doesn't exist at /root/.cache/ms-playwright/...".
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . .

# Expose the Gradio port
EXPOSE 7860

# Run the Gradio app
CMD ["python", "app2.py"]
