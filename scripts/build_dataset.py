"""Build training data for Q-Guardian ("make the fuel").

Downloads a real, labeled prompt-injection dataset over plain HTTP
(no huggingface `datasets`/pandas needed) and/or exports the prompts you
collected in the interactive CLI, so you can then train the models.

Usage:
    python scripts/build_dataset.py                    # download deepset benchmark
    python scripts/build_dataset.py --from-memory      # export your CLI prompts
    python scripts/build_dataset.py --train            # download AND train right away
    python scripts/build_dataset.py --from-memory --train

Options:
    --from-memory   also export prompts collected in the CLI (qg_memory.jsonl)
    --train         chain into scripts/train_data.py after building
    --max-samples N samples per class used for training (default 200)
    --out DIR       where dataset files are written (default: data)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
MEMORY_FILE = ROOT / "examples" / "qg_memory.jsonl"
ROWS_API = "https://datasets-server.huggingface.co/rows"
SOURCE = "deepset/prompt-injections"  # 662 rows, text + label (0/1), Apache-2.0


def fetch_rows(repo: str, split: str, length: int = 100):
    """Paginate over the HF datasets-server rows API for a split."""
    offset = 0
    while True:
        resp = requests.get(
            ROWS_API,
            params={
                "dataset": repo,
                "config": "default",
                "split": split,
                "offset": offset,
                "length": length,
            },
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("rows", [])
        if not rows:
            break
        for r in rows:
            yield r["row"]
        offset += len(rows)
        if offset >= payload.get("num_rows_total", 0):
            break


def download_deepset(out_path: Path) -> int:
    print(f"Downloading {SOURCE} (train + test splits)...")
    rows_written = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for split in ("train", "test"):
            for row in fetch_rows(SOURCE, split):
                text = (row.get("text") or "").strip()
                label = row.get("label")
                if not text or label not in (0, 1):
                    continue
                f.write(json.dumps({"text": text, "label": int(label)}, ensure_ascii=False) + "\n")
                rows_written += 1
    print(f"  wrote {rows_written} labeled rows -> {out_path}")
    return rows_written


def export_memory(out_path: Path) -> int:
    if not MEMORY_FILE.exists():
        print("  no CLI memory found; skipping export")
        return 0
    seen: set[str] = set()
    rows_written = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for line in MEMORY_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = (rec.get("text") or "").strip()
            if rec.get("label") is None or not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            f.write(
                json.dumps({"text": text, "label": int(rec["label"])}, ensure_ascii=False) + "\n"
            )
            rows_written += 1
    print(f"  wrote {rows_written} unique CLI prompts -> {out_path}")
    return rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-memory", action="store_true", help="also export prompts collected in the CLI"
    )
    parser.add_argument(
        "--train", action="store_true", help="chain into scripts/train_data.py after building"
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=200,
        help="samples per class used for training (default 200)",
    )
    parser.add_argument(
        "--qsvm-samples", type=int, default=60, help="samples per class for the QSVM (default 60)"
    )
    parser.add_argument("--out", default=str(ROOT / "data"), help="where dataset files are written")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    datasets = []
    ds = out_dir / "prompt_injections.jsonl"
    n = download_deepset(ds)
    datasets.append((str(ds), n))

    if args.from_memory:
        mem = out_dir / "user_collected.jsonl"
        n = export_memory(mem)
        if n:
            datasets.append((str(mem), n))

    if not args.train:
        print("\nNext step: train the models, e.g.:")
        print(f"  python scripts/train_data.py {datasets[0][0]} --max-samples {args.max_samples}")
        return

    for path, _ in datasets:
        t0 = time.monotonic()
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "train_data.py"),
            path,
            "--base",
            "--max-samples",
            str(args.max_samples),
            "--qsvm-samples",
            str(args.qsvm_samples),
        ]
        print(f"\n>>> Training on {path} ...")
        subprocess.run(cmd, cwd=str(ROOT))
        print(f"    finished in {time.monotonic() - t0:.1f}s")


if __name__ == "__main__":
    main()
