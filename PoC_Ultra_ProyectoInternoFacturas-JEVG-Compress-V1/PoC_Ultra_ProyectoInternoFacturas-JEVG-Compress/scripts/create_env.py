"""Crea .env a partir de .env.example con una SECRET_KEY aleatoria. Nunca sobrescribe un .env existente."""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def create_env(root: Path = ROOT) -> bool:
    env_file = root / ".env"
    if env_file.exists():
        return False
    lines = (root / ".env.example").read_text(encoding="utf-8").splitlines()
    secret = f"SECRET_KEY={secrets.token_urlsafe(64)}"
    if any(line.startswith("SECRET_KEY=") for line in lines):
        lines = [secret if line.startswith("SECRET_KEY=") else line for line in lines]
    else:
        lines.append(secret)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


if __name__ == "__main__":
    if create_env():
        print(".env creado con una SECRET_KEY aleatoria.")
    else:
        print(".env ya existe; no se modifico.")
