#!/bin/bash
# Azure App Service startup script

cd /home/site/wwwroot

# Aplicar migraciones de base de datos
echo "Aplicando migraciones Alembic..."
python -m alembic upgrade head

# Iniciar servidor
echo "Iniciando Gunicorn..."
exec gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --keep-alive 5 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --access-logfile - \
  --error-logfile -
