from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys
from dotenv import load_dotenv

# Permet d'importer ton application FastAPI si nécessaire
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import de tes modèles SQLAlchemy
from db_setting import Base  # <--- remplace par ton module où se trouve Base


load_dotenv()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db_setting import Base

config = context.config

# Lire l'URL depuis .env
db_url = os.getenv("db_url_local")
config.set_main_option("sqlalchemy.url", db_url.replace("+asyncpg",""))
fileConfig(config.config_file_name)

target_metadata = Base.metadata
# Configuration Alembic
config = context.config

# Lecture du logging depuis alembic.ini
fileConfig(config.config_file_name)

# MetaData pour autogenerate
target_metadata = Base.metadata

# ---------------------------------------------------------
# Fonction pour migration en mode synchrone
# ---------------------------------------------------------
def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------
# Lancement
# ---------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()