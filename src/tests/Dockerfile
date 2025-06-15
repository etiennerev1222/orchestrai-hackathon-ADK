# src/tests/Dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY src /app/src

# --- NOUVEAU: Copier le certificat CA ---
COPY src/config/cluster-ca.crt /app/src/config/cluster-ca.crt 

RUN pip install --no-cache-dir -r /app/src/tests/requirements.txt

ENV PYTHONPATH=/app
CMD ["python", "src/tests/k8s_iam_test_server.py"]