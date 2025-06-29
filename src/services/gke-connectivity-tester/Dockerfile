FROM python:3.11-slim-buster

# Installe les utilitaires DNS (dig, nslookup) et ping
RUN apt-get update && \
    apt-get install -y --no-install-recommends dnsutils iputils-ping && rm -rf /var/lib/apt/lists/*

# Définit le répertoire de travail dans le conteneur
WORKDIR /app

# Copie le fichier requirements.txt et installe les dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie le code de l'application
COPY main.py .

# Expose le port sur lequel l'application Flask écoute (Cloud Run attend 8080 par défaut)
EXPOSE 8080

# Commande pour démarrer l'application Flask avec Gunicorn
# Cloud Run injecte la variable d'environnement PORT, qui est 8080 par défaut.
# Gunicorn doit écouter sur 0.0.0.0:$PORT.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]
# Note: "main:app" signifie qu'il cherche l'application Flask nommée 'app' dans le fichier 'main.py'.