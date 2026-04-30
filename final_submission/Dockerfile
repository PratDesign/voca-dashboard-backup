FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
EXPOSE 8080

# Use a startup script to run both server.py and streamlit
COPY start.sh .
RUN chmod +x start.sh
CMD ["./start.sh"]