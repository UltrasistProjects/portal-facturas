import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.middleware import request_context

# Atributos propios de LogRecord: todo lo demas proviene de `extra` y se emite como campo del evento.
_STANDARD_ATTRIBUTES = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Una linea JSON por evento, con request_id y user_id de la peticion en curso (AUDITORIA COD-05)."""

    def format(self, record: logging.LogRecord) -> str:
        context = request_context()
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": context.get("request_id"),
        }
        if context.get("user_id") is not None:
            payload["user_id"] = context["user_id"]
        payload.update(
            {key: value for key, value in vars(record).items() if key not in _STANDARD_ATTRIBUTES and key[0] != "_"}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(log_dir: Path, debug: bool = False) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = JsonFormatter()
    file_handler = RotatingFileHandler(log_dir / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, handlers=[console_handler, file_handler], force=True)
    # httpx y httpcore registran cada URL solicitada (codigos de autorizacion, correos en las busquedas de Keycloak):
    # solo sus advertencias. Las llamadas a Keycloak ya dejan su propio evento sin datos sensibles (keycloak.admin).
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
