"""Genera un ZIP distribuible sin secretos ni datos (AUDITORIA SEC-09).

Con Git, empaqueta solo archivos versionados (git ls-files); sin Git, recorre el arbol. En ambos casos aplica la
lista de exclusion y, al terminar, verifica el ZIP: si contiene algo prohibido, lo elimina y falla.
Uso: python scripts/package_release.py [--output dist/portal.zip] [--no-git]
"""

import argparse
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_TOP_LEVEL = {".venv", "backups", "Microsoft", ".pytest_cache", "htmlcov", "dist", "logs", "storage"}
FORBIDDEN_NAMES = {".env", ".coverage", "coverage.xml"}


def is_forbidden(relative: str) -> bool:
    """True para secretos, datos, logs, almacenamiento, respaldos, entornos y caches (los .gitkeep se permiten)."""
    parts = relative.replace("\\", "/").split("/")
    name = parts[-1]
    if name == ".gitkeep":
        return False
    if name in FORBIDDEN_NAMES or parts[0] in FORBIDDEN_TOP_LEVEL:
        return True
    if "__pycache__" in parts or name.endswith((".pyc", ".pyo")):
        return True
    return parts[0] == "data" and len(parts) == 2 and (".db" in name or ".sqlite" in name)


def git_files(root: Path) -> list[str] | None:
    try:
        result = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return [name for name in result.stdout.decode().split("\0") if name]


def tree_files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def build_package(root: Path, output: Path, files: list[str] | None = None, use_git: bool = True) -> Path:
    """Crea el ZIP; `files` permite fijar la seleccion (solo para probar la verificacion posterior)."""
    if files is None:
        candidates = (git_files(root) if use_git else None) or tree_files(root)
        files = [name for name in candidates if not is_forbidden(name) and (root / name).is_file()]
    output.parent.mkdir(parents=True, exist_ok=True)
    prefix = root.name
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(root / name, f"{prefix}/{name}")
    with zipfile.ZipFile(output) as archive:
        offending = [name for name in archive.namelist() if is_forbidden(name.split("/", 1)[1])]
    if offending:
        output.unlink()
        raise RuntimeError(f"El paquete incluia archivos prohibidos y se elimino: {offending[:10]}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / f"{ROOT.name}-{stamp}.zip")
    parser.add_argument("--no-git", action="store_true", help="ignora Git y recorre el arbol con la lista de exclusion")
    args = parser.parse_args()
    try:
        package = build_package(ROOT, args.output, use_git=not args.no_git)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Paquete generado: {package}")


if __name__ == "__main__":
    sys.exit(main())
