"""Build script for Q-Guardian package."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def _load_pyproject() -> dict[str, object]:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def _clean() -> None:
    for p in (DIST, BUILD):
        if p.exists():
            shutil.rmtree(p)
            print(f"  removed {p.relative_to(ROOT)}")
    for egg in ROOT.glob("*.egg-info"):
        shutil.rmtree(egg)
        print(f"  removed {egg.relative_to(ROOT)}")


def _build() -> None:
    subprocess.check_call([sys.executable, "-m", "build", "--outdir", str(DIST)])


def _list_wheel(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return sorted(zf.namelist())


def _list_sdist(path: Path) -> list[str]:
    with tarfile.open(path) as tf:
        return sorted(tf.getnames())


def main() -> None:
    print("=== Q-Guardian Build ===\n")

    pyproject = _load_pyproject()
    project = pyproject["project"]
    print(f"Package: {project['name']} {project['version']}\n")

    print("Cleaning previous builds...")
    _clean()

    print("\nBuilding distribution packages...")
    _build()

    print("\nBuild artifacts:")
    for f in sorted(DIST.iterdir()):
        print(f"  {f.name}  ({f.stat().st_size:,} bytes)")

    wheels = sorted(DIST.glob("*.whl"))
    sdists = sorted(DIST.glob("*.tar.gz"))

    if wheels:
        print(f"\nWheel contents ({wheels[0].name}):")
        for name in _list_wheel(wheels[0]):
            print(f"  {name}")

    if sdists:
        print(f"\nSdist contents ({sdists[0].name}):")
        for name in _list_sdist(sdists[0]):
            print(f"  {name}")

    print("\n=== Build complete ===")


if __name__ == "__main__":
    main()
