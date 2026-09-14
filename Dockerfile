FROM python:3.11-slim

# Configure debconf to avoid warnings
ENV DEBIAN_FRONTEND=noninteractive


WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files explicitly
COPY api/ api/
COPY knowledge-base/ knowledge-base/
COPY app.py .
COPY startup.sh .

# Make startup script executable
RUN chmod +x startup.sh

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8080

# Run the application with startup script
CMD ["./startup.sh"]
