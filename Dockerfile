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

# Copy application code
COPY . .

# Expose the Gradio port
EXPOSE 7860

# Run the Gradio app
CMD ["python", "app2.py"]
