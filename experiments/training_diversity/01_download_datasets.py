"""Download candidate public jailbreak/harmful-content datasets to local JSONL.

Sources (all public, no HF token required), accessed 2026-08-16:

- TrustAIRLab/in-the-wild-jailbreak-prompts (jailbreak_2023_12_25 / regular_2023_12_25)
  https://huggingface.co/datasets/TrustAIRLab/in-the-wild-jailbreak-prompts
- JailbreakV-28K/JailBreakV-28k (config JailBreakV_28K)
  https://huggingface.co/datasets/JailbreakV-28K/JailBreakV-28k
- mlabonne/harmful_behaviors (default, train+test)
  https://huggingface.co/datasets/mlabonne/harmful_behaviors

Output: experiments/training_diversity/data_raw/*.jsonl
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
RAW = HERE / "data_raw"
RAW.mkdir(parents=True, exist_ok=True)

BASE = "https://datasets-server.huggingface.co/rows"


def fetch_rows(dataset: str, config: str, split: str, offset: int, length: int = 100) -> dict:
    url = f"{BASE}?dataset={dataset}&config={config}&split={split}&offset={offset}&length={length}"
    for attempt in range(5):
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(2 + attempt * 2)
    raise RuntimeError(f"failed: {url}")


def download(
    dataset: str,
    config: str,
    split: str,
    out_name: str,
    cols: tuple[str, ...] | None = None,
    max_rows: int | None = None,
    offset_start: int = 0,
) -> int:
    """Fetch all rows for a split and write JSONL. Returns row count."""
    out = RAW / out_name
    if out.exists():
        with open(out, encoding="utf-8") as f:
            return sum(1 for _ in f)

    count = 0
    offset = offset_start
    with open(out, "w", encoding="utf-8") as f:
        while True:
            data = fetch_rows(dataset, config, split, offset)
            rows = data.get("rows", [])
            if not rows:
                break
            for row in rows:
                rec = row.get("row", {})
                if cols is not None:
                    rec = {c: rec.get(c) for c in cols}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += len(rows)
            offset += len(rows)
            if max_rows is not None and count >= max_rows:
                break
            if len(rows) < 100:
                break
            print(f"  {out_name}: {count} rows")
    print(f"{out_name}: {count} total")
    return count


if __name__ == "__main__":
    download(
        "TrustAIRLab/in-the-wild-jailbreak-prompts",
        "jailbreak_2023_12_25",
        "train",
        "trustair_jailbreaks.jsonl",
        cols=("prompt", "jailbreak", "source", "platform", "date"),
    )
    download(
        "TrustAIRLab/in-the-wild-jailbreak-prompts",
        "regular_2023_12_25",
        "train",
        "trustair_regular.jsonl",
        cols=("prompt", "jailbreak", "source", "platform", "date"),
        max_rows=3500,
    )
    download(
        "JailbreakV-28K/JailBreakV-28k",
        "JailBreakV_28K",
        "JailBreakV_28K",
        "jailbreakv.jsonl",
        cols=("jailbreak_query", "redteam_query", "policy", "format", "from"),
        max_rows=5900,
    )
    download(
        "mlabonne/harmful_behaviors",
        "default",
        "train",
        "harmful_behaviors_train.jsonl",
        cols=("text",),
    )
    download(
        "mlabonne/harmful_behaviors",
        "default",
        "test",
        "harmful_behaviors_test.jsonl",
        cols=("text",),
    )
