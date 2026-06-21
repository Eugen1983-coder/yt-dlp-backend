# Use official Python slim image
FROM python:3.11-slim

# Install system dependencies: curl (for deno install), ffmpeg (for yt-dlp)
RUN apt-get update && apt-get install -y curl ffmpeg && rm -rf /var/lib/apt/lists/*

# Install Deno runtime
RUN curl -fsSL https://deno.land/install.sh | sh

# Add Deno to PATH
ENV PATH="/root/.deno/bin:${PATH}"

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app code
COPY . .

# Expose port 5000
EXPOSE 5000

# Set environment variable for yt-dlp JS runtime
ENV YT_DLP_JS_RUNTIME=deno

# Run the app with Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
