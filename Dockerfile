FROM python:3.11-slim

# Install ffmpeg and clean up apt cache to reduce image size
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py .
COPY templates/ ./templates/

# Expose the API and Stream port
EXPOSE 38080

# Run the FastAPI app
CMD ["python", "main.py"]
