from sqlalchemy import text

from support_agent.core.database import get_engine
from support_agent.core.schema import initialize_schema


def main() -> None:
    initialize_schema(get_engine())
    with get_engine().connect() as connection:
        database_name = connection.execute(text("SELECT current_database()")).scalar_one()
    print(f"Initialized application schema in database '{database_name}'.")


if __name__ == "__main__":
    main()
