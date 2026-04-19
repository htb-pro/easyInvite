# Image Python officielle
FROM python:3.11-slim

# Empêcher les fichiers .pyc et forcer l'affichage des logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Dossier de travail
WORKDIR /app

# --- INSTALLATION DES DÉPENDANCES SYSTÈME ---
# On regroupe tout ici : libzbar0, libgl1 ET les outils pour pycairo (gcc, libcairo, etc.)
RUN apt-get update && apt-get install -y \
    libzbar0 \
    libgl1 \
    gcc \
    pkg-config \
    libcairo2-dev \
    libpkgconf-dev \
    && rm -rf /var/lib/apt/lists/*

# Copier le fichier des dépendances
COPY requirement.txt .

# --- INSTALLATION DES DÉPENDANCES PYTHON ---
# Maintenant que gcc est installé, pycairo pourra se compiler sans erreur
RUN pip install --no-cache-dir -r requirement.txt

# Copier tout le reste du projet
COPY . .

# Port utilisé par Render
EXPOSE 10000

# Commande de lancement
CMD ["uvicorn", "rooting:Apk", "--host", "0.0.0.0", "--port", "10000"]