# Utilise une image Python de base
FROM python:3.11-slim

# Définit le répertoire de travail dans le conteneur
WORKDIR /app

# Copie uniquement le code source nécessaire
COPY ./src /app/src

# Installe les dépendances Python (incluant la librairie kubernetes)
RUN pip install --no-cache-dir -r /app/src/tests/requirements.txt

# La commande pour démarrer le serveur de l'Environment Manager
CMD ["python", "-m", "src.services.environment_manager.server"]