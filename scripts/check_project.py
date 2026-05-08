from __future__ import annotations
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class CheckResult:
    ok: bool
    warnings: list[str]
    errors: list[str]


def _print_header() -> None:
    print("=== SIRAN CHECK PROJECT ===")


def _iter_py_files(dir_path: Path) -> list[Path]:
    if not dir_path.exists():
        return []
    return sorted([p for p in dir_path.rglob("*.py") if p.is_file()])


def _compile_targets() -> list[Path]:
    targets: list[Path] = []
    for p in [
        ROOT / "app.py",
        ROOT / "config.py",
        ROOT / "src" / "system_core.py",
        ROOT / "src" / "video_processor.py",
    ]:
        if p.exists():
            targets.append(p)

    targets += _iter_py_files(ROOT / "src" / "routes")
    targets += _iter_py_files(ROOT / "src" / "services")
    targets += _iter_py_files(ROOT / "tests")
    return targets


def check_py_compile() -> CheckResult:
    warnings: list[str] = []
    errors: list[str] = []

    targets = _compile_targets()
    if not targets:
        errors.append("No se encontraron archivos .py para compilar.")
        return CheckResult(ok=False, warnings=warnings, errors=errors)

    import py_compile

    for p in targets:
        try:
            py_compile.compile(str(p), doraise=True)
        except Exception as e:
            errors.append(f"PY_COMPILE_ERROR {p}: {e!r}")

    return CheckResult(ok=(len(errors) == 0), warnings=warnings, errors=errors)


def check_pytest() -> CheckResult:
    warnings: list[str] = []
    errors: list[str] = []

    pytest_available = True
    try:
        import pytest  # noqa: F401
    except Exception:
        pytest_available = False

    cmd = [sys.executable, "-m", "pytest", "tests"]
    if not pytest_available:
        # Mensaje claro (instalar en ESTE intérprete).
        errors.append(
            f"pytest no está instalado para este Python ({sys.executable}). Instala con: {sys.executable} -m pip install pytest"
        )
        # Fallback Windows: intentar con `py -3.11` si existe (solo para ayudar en setups con múltiples Pythons).
        if os.name == "nt":
            try:
                probe = subprocess.run(
                    ["py", "-3.11", "-c", "import sys; print(sys.executable)"],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if probe.returncode == 0:
                    cmd = ["py", "-3.11", "-m", "pytest", "tests"]
                    warnings.append("pytest no está en el Python actual; intentando con `py -3.11` como fallback.")
                    # No marcar error todavía: si el fallback funciona, el check pasa.
                    errors.pop()
                else:
                    return CheckResult(ok=False, warnings=warnings, errors=errors)
            except Exception:
                return CheckResult(ok=False, warnings=warnings, errors=errors)
        else:
            return CheckResult(ok=False, warnings=warnings, errors=errors)

    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        errors.append("pytest timeout (>600s).")
        return CheckResult(ok=False, warnings=warnings, errors=errors)
    except Exception as e:
        errors.append(f"pytest error: {e!r}")
        return CheckResult(ok=False, warnings=warnings, errors=errors)

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        errors.append("pytest falló.")
        if out:
            errors.append(out)
        if err:
            errors.append(err)
        return CheckResult(ok=False, warnings=warnings, errors=errors)

    # Extraer resumen tipo "36 passed"
    summary = ""
    for line in out.splitlines()[::-1]:
        if "passed" in line and ("==" in line or "passed in" in line):
            summary = line.strip()
            break
    if summary:
        warnings.append(f"pytest: {summary}")
    else:
        warnings.append("pytest: OK")

    return CheckResult(ok=True, warnings=warnings, errors=errors)


def _exists_any(paths: Iterable[Path]) -> bool:
    for p in paths:
        if p.exists():
            return True
    return False


def check_sensitive_files() -> CheckResult:
    warnings: list[str] = []
    errors: list[str] = []

    # Archivos/directorios "sensibles" (existencia local es normal, pero debe advertirse).
    sensitive_paths = [
        ROOT / ".env",
        ROOT / "config_camara.json",
        ROOT / "uploads",
        ROOT / "static" / "results",
        ROOT / "static" / "evidence",
        ROOT / "static" / "top_detections",
        ROOT / "dataset_entrenamiento",
        ROOT / "dataset_recoleccion",
        ROOT / "runs",
    ]
    for p in sensitive_paths:
        if p.exists():
            warnings.append(f"Existe localmente: {p.relative_to(ROOT)} (verifica .gitignore / no subir)")

    # Patrones por extensión en root (solo advertir).
    patterns = ["*.db", "*.sqlite", "*.sqlite3", "*.pt", "*.onnx"]
    for pat in patterns:
        matches = sorted([p for p in ROOT.rglob(pat) if p.is_file()])
        # Evitar spamear; reportar solo los primeros N.
        if matches:
            shown = matches[:10]
            warnings.append(f"Encontrados {len(matches)} archivos {pat} (mostrando {len(shown)}):")
            for m in shown:
                warnings.append(f"  - {m.relative_to(ROOT)}")

    return CheckResult(ok=True, warnings=warnings, errors=errors)


def check_git_status() -> CheckResult:
    warnings: list[str] = []
    errors: list[str] = []

    git = "git.exe" if os.name == "nt" else "git"
    try:
        proc = subprocess.run([git, "--version"], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            warnings.append("git no disponible; omitiendo git status.")
            return CheckResult(ok=True, warnings=warnings, errors=errors)
    except Exception:
        warnings.append("git no disponible; omitiendo git status.")
        return CheckResult(ok=True, warnings=warnings, errors=errors)

    proc2 = subprocess.run([git, "status", "--porcelain"], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
    out = (proc2.stdout or "").rstrip()
    if proc2.returncode != 0:
        warnings.append("No se pudo ejecutar git status.")
        return CheckResult(ok=True, warnings=warnings, errors=errors)

    if not out.strip():
        warnings.append("working tree clean")
        return CheckResult(ok=True, warnings=warnings, errors=errors)

    warnings.append("cambios pendientes en working tree:")
    for line in out.splitlines():
        warnings.append(f"  {line}")
    return CheckResult(ok=True, warnings=warnings, errors=errors)


def main() -> int:
    _print_header()

    all_warnings: list[str] = []
    all_errors: list[str] = []

    print("\n[1/4] Compilación Python...")
    r1 = check_py_compile()
    if r1.ok:
        print("OK")
    else:
        print("ERROR")
    all_warnings += r1.warnings
    all_errors += r1.errors

    print("\n[2/4] Pytest...")
    r2 = check_pytest()
    if r2.ok:
        print("OK")
    else:
        print("ERROR")
    all_warnings += r2.warnings
    all_errors += r2.errors

    print("\n[3/4] Archivos sensibles...")
    r3 = check_sensitive_files()
    print("OK" if r3.ok else "ERROR")
    all_warnings += r3.warnings
    all_errors += r3.errors

    print("\n[4/4] Git status...")
    r4 = check_git_status()
    print("OK" if r4.ok else "ERROR")
    all_warnings += r4.warnings
    all_errors += r4.errors

    # Report detail
    if all_warnings:
        print("\n--- WARNINGS ---")
        for w in all_warnings:
            print(f"[WARN] {w}")

    if all_errors:
        print("\n--- ERRORS ---")
        for e in all_errors:
            print(f"[ERROR] {e}")

    if all_errors:
        print("\nRESULTADO FINAL: ERROR")
        return 1
    if all_warnings:
        print("\nRESULTADO FINAL: OK CON WARNINGS")
        return 0
    print("\nRESULTADO FINAL: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
