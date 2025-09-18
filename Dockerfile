FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY proxy/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY proxy /app/proxy
ENV PYTHONPATH=/app

EXPOSE 8080
CMD ["uvicorn", "proxy.main:app", "--host", "0.0.0.0", "--port", "8080"]
