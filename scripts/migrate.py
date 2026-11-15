import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from apps.api.config import validate_deployment_configuration


def main() -> None:
    validate_deployment_configuration()
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    engine.dispose()
    command.upgrade(Config("alembic.ini"), "head")


if __name__ == "__main__":
    main()
