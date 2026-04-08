FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything else
COPY . .

ENV PYTHONPATH=/app
EXPOSE 8080

# Clean single-line command to avoid shell parsing errors
CMD ["streamlit", "run", "parent_dashboard.py", "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true"]
