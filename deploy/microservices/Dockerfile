FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-microservices.txt && useradd --create-home invax
COPY . .
RUN python scripts/preparar_pwa.py && chown -R invax:invax /app
USER invax
EXPOSE 8080
CMD ["python", "-m", "backend.microservices.run"]
