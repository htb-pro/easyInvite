# Image Python officielle
FROM python:3.11-slim

# Empêcher les fichiers .pyc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Installer les dépendances système (IMPORTANT pour pyzbar)
RUN apt-get update && apt-get install -y \
    libzbar0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Dossier de travail
WORKDIR /app

# Copier les requirements
COPY requirement.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirement.txt

# Copier tout le projet
COPY . .

# Port utilisé par Render
EXPOSE 10000

# Commande de lancement (ADAPTE si besoin)
CMD ["uvicorn", "rooting:Apk", "--host", "0.0.0.0", "--port", "10000"]