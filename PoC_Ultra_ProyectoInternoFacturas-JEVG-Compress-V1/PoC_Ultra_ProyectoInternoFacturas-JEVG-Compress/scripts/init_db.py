from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.database import Base, engine
import app.models  # noqa: F401

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print("Base de datos inicializada.")

