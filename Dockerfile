FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install build deps and runtime
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app sources
COPY . .

EXPOSE 5000

# Use gunicorn for production-like behavior inside container
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
