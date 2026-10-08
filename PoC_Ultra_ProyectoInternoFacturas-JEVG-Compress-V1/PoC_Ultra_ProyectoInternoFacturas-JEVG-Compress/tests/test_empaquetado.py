import subprocess
import zipfile

import pytest

from scripts.package_release import build_package, is_forbidden

ALLOWED = [
    "app/main.py",
    ".env.example",
    "README.md",
    "data/demo_documents/cfdi.xml",
    "logs/.gitkeep",
    "storage/invoices/.gitkeep",
]
FORBIDDEN = [
    ".env",
    "data/invoice_portal.db",
    "data/invoice_portal.db-wal",
    "data/invoice_portal.db-shm",
    "logs/app.log",
    "storage/invoices/1/factura.pdf",
    "storage/suppliers/2/rfc.txt",
    "backups/20260924-120000/manifest.json",
    ".venv/bin/python",
    ".pytest_cache/v/cache/nodeids",
    "app/__pycache__/main.cpython-312.pyc",
    "Microsoft/Windows/PowerShell/ModuleAnalysisCache",
    ".coverage",
]


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "portal"
    for name in ALLOWED + FORBIDDEN:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"contenido de {name}", encoding="utf-8")
    return root


def packaged(output) -> set[str]:
    with zipfile.ZipFile(output) as archive:
        return {name.split("/", 1)[1] for name in archive.namelist()}


def test_paquete_sin_secretos_ni_datos(project, tmp_path):
    output = build_package(project, tmp_path / "dist" / "portal.zip", use_git=False)
    assert packaged(output) == set(ALLOWED)


def test_paquete_con_git_incluye_solo_versionados(project, tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "add", "app/main.py", "README.md", "logs/.gitkeep"], cwd=project, check=True)
    subprocess.run(["git", "add", "-f", ".env"], cwd=project, check=True)  # aun versionado por error, se excluye
    output = build_package(project, tmp_path / "portal.zip")
    assert packaged(output) == {"app/main.py", "README.md", "logs/.gitkeep"}


def test_verificacion_posterior_elimina_el_paquete(project, tmp_path):
    output = tmp_path / "portal.zip"
    with pytest.raises(RuntimeError, match=r"\.env"):
        build_package(project, output, files=["app/main.py", ".env"])
    assert not output.exists()


@pytest.mark.parametrize("name", FORBIDDEN)
def test_reglas_de_exclusion(name):
    assert is_forbidden(name)


@pytest.mark.parametrize("name", ALLOWED)
def test_archivos_permitidos(name):
    assert not is_forbidden(name)
