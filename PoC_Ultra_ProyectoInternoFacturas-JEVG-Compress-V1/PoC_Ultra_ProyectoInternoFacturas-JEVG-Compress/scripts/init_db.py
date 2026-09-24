import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.models  # noqa: F401
from app.core.database import Base, engine

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print("Base de datos inicializada.")
