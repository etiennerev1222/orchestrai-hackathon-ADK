# Utilise une image Python de base
FROM python:3.11-slim

# Définit le répertoire de travail dans le conteneur
WORKDIR /app

# Copie uniquement le code source nécessaire
COPY ./src /app/src

# Installe les dépendances Python
RUN pip install --no-cache-dir -r /app/src/tests/requirements.txt

# La commande pour démarrer le serveur du Development Agent
CMD ["python", "-m", "src.agents.development_agent.server"]