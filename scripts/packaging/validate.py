"""Validate Q-Guardian package metadata and structure."""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PYPROJECT_FIELDS = [
    "name",
    "version",
    "description",
    "license",
    "requires-python",
]


def _load_pyproject() -> dict[str, object]:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def _get_init_version() -> str | None:
    init = ROOT / "src" / "q_guardian" / "__init__.py"
    if not init.exists():
        return None
    for line in init.read_text().splitlines():
        if line.startswith("__version__"):
            return line.split("=")[1].strip().strip('"').strip("'")
    return None


def _validate_pyproject(project: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_PYPROJECT_FIELDS:
        if field not in project:
            errors.append(f"Missing required field: {project.get('name', '?')}.{field}")
    return errors


def _validate_version_match(pyproject_version: str, init_version: str | None) -> list[str]:
    errors: list[str] = []
    if init_version is None:
        errors.append("Could not read __version__ from src/q_guardian/__init__.py")
    elif pyproject_version != init_version:
        errors.append(
            f"Version mismatch: pyproject.toml={pyproject_version}, __init__.py={init_version}"
        )
    return errors


def _validate_files() -> list[str]:
    errors: list[str] = []
    for name in ("LICENSE", "README.md"):
        p = ROOT / name
        if not p.exists():
            errors.append(f"Missing file: {name}")
        elif p.stat().st_size == 0:
            errors.append(f"Empty file: {name}")
    return errors


def _validate_exports() -> list[str]:
    errors: list[str] = []
    init = ROOT / "src" / "q_guardian" / "__init__.py"
    if not init.exists():
        errors.append("src/q_guardian/__init__.py not found")
        return errors

    try:
        tree = ast.parse(init.read_text())
    except SyntaxError as exc:
        errors.append(f"src/q_guardian/__init__.py failed to parse: {exc}")
        return errors

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                imports.add(alias.asname or alias.name.split(".", 1)[0])

    all_list: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            )
            and isinstance(node.value, (ast.List, ast.Tuple))
        ):
            all_list.extend(
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            )

    for name in all_list:
        if name not in imports:
            errors.append(f"__all__ entry '{name}' has no corresponding import")

    return errors


def main() -> None:
    print("=== Q-Guardian Package Validation ===\n")
    all_errors: list[str] = []

    pyproject = _load_pyproject()
    project = pyproject.get("project", {})

    print("1. pyproject.toml required fields...")
    errs = _validate_pyproject(project)
    all_errors.extend(errs)
    if not errs:
        print("   OK")

    print("\n2. Version consistency...")
    pyproject_version = project.get("version", "")
    init_version = _get_init_version()
    errs = _validate_version_match(str(pyproject_version), init_version)
    all_errors.extend(errs)
    if not errs:
        print("   OK")

    print("\n3. Required files...")
    errs = _validate_files()
    all_errors.extend(errs)
    if not errs:
        print("   OK")

    print("\n4. __all__ export validation...")
    errs = _validate_exports()
    all_errors.extend(errs)
    if not errs:
        print("   OK")

    print()
    if all_errors:
        print("VALIDATION FAILED:")
        for e in all_errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("All validations passed.")


if __name__ == "__main__":
    main()
