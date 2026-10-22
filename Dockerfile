FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 INVENTARIO_DATA_DIR=/app/data PORT=8080
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-servidor.txt && useradd --create-home inventario
COPY . .
RUN mkdir -p /app/data && chown -R inventario:inventario /app
USER inventario
EXPOSE 8080
CMD ["python", "-m", "backend.iniciar_servidor"]
