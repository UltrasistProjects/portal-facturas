import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path, debug: bool = False) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_handler = RotatingFileHandler(log_dir / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, handlers=[logging.StreamHandler(), file_handler], force=True)
