
from app.database import Base, engine
from app import models


def initialize_database():
    Base.metadata.create_all(bind=engine)
    print("Garuda Ops database tables initialized.")

    print("Tables created:", list(Base.metadata.tables.keys()))


if __name__ == "__main__":
    initialize_database()
