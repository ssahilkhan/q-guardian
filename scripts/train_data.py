"""Train Q-Guardian models (ML + quantum QSVM) from a labeled prompt dataset.

Supported inputs:
  CSV     : columns `text` (or `prompt`/`statement`) and `label`
  JSONL   : one {"text": ..., "label": ...} object per line
  JSON    : a list of {"text": ..., "label": ...} objects

Label auto-mapping:
  0 / benign / safe / allow            -> benign (0)
  1 / malicious / unsafe / threat /
    escalate / block / deny            -> malicious (1)

Usage:
    python scripts/train_data.py my_dataset.csv
    python scripts/train_data.py my_dataset.jsonl --base
    python scripts/train_data.py my_dataset.json --replace --max-samples 500

Options:
    --base          ALSO keep the built-in 20-prompt demo corpus (default: replace it)
    --replace       explicitly replace built-in corpus (same as omitting --base)
    --max-samples N cap total training samples per class (keeps QSVM fast)
    --qsvm-samples N cap the QSVM training subset per class (default 60;
                   classical ML still trains on the full dataset)
    --state-dir DIR where to save the trained models (default: examples/qg_state)

After training, run `python scripts/prompt_cli.py` and the models you trained
are the ones used.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(30),
    processors=[
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "examples" / "prompt_test_harness.py"
DEFAULT_STATE_DIR = ROOT / "examples" / "qg_state"

_spec = importlib.util.spec_from_file_location("prompt_test_harness", HARNESS)
assert _spec is not None and _spec.loader is not None, "harness import failed"
HARNESS_MOD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(HARNESS_MOD)
Pipeline = HARNESS_MOD.Pipeline


def parse_label(raw) -> int | None:
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, (int, float)):
        return int(raw) if int(raw) in (0, 1) else None
    s = str(raw).strip().lower()
    if s in ("0", "benign", "safe", "allow", "ok", "good"):
        return 0
    if s in ("1", "malicious", "unsafe", "threat", "escalate", "block",
             "deny", "bad", "attack"):
        return 1
    return None


def load_dataset(path: Path) -> list[tuple[str, int]]:
    samples: list[tuple[str, int]] = []
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                text = obj.get("text") or obj.get("prompt") or obj.get("statement")
                label = parse_label(obj.get("label"))
                if text and label is not None:
                    samples.append((str(text), label))
    elif path.suffix.lower() == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for obj in data:
            text = obj.get("text") or obj.get("prompt") or obj.get("statement")
            label = parse_label(obj.get("label"))
            if text and label is not None:
                samples.append((str(text), label))
    elif path.suffix.lower() == ".csv":
        with open(path, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                text = (row.get("text") or row.get("prompt")
                        or row.get("statement") or "")
                label = parse_label(row.get("label"))
                if text.strip() and label is not None:
                    samples.append((text.strip(), label))
    else:
        raise SystemExit(
            f"Unsupported file type: {path.suffix} "
            f"(use .csv, .jsonl, .ndjson or .json)")
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", help="path to labeled dataset (csv/jsonl/json)")
    parser.add_argument("--base", action="store_true",
                        help="also keep the built-in 20-prompt demo corpus")
    parser.add_argument("--replace", action="store_true",
                        help="explicitly replace the built-in corpus (default)")
    parser.add_argument("--max-samples", type=int, default=200,
                        help="max training samples kept per class (default 200)")
    parser.add_argument("--qsvm-samples", type=int, default=60,
                        help="max samples per class for QSVM (default 60)")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR),
                        help="where trained models are saved")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found: {dataset_path}")

    raw = load_dataset(dataset_path)
    if not raw:
        raise SystemExit("No valid (text, label) samples found in dataset.")

    benign = [s for s in raw if s[1] == 0]
    malicious = [s for s in raw if s[1] == 1]
    print(f"Dataset: {len(raw)} samples "
          f"({len(benign)} benign / {len(malicious)} malicious)")

    if args.max_samples:
        random.Random(42).shuffle(benign)
        random.Random(42).shuffle(malicious)
        benign = benign[:args.max_samples]
        malicious = malicious[:args.max_samples]
        print(f"After capping to {args.max_samples}/class: "
              f"{len(benign)} benign / {len(malicious)} malicious")

    corpus: list[tuple[str, int]] = []
    if args.base:
        corpus += [(t, 0) for t in HARNESS_MOD._TRAIN_BENIGN] \
               + [(t, 1) for t in HARNESS_MOD._TRAIN_MALICIOUS]
    corpus += benign + malicious

    qsvm_corpus: list[tuple[str, int]] | None = None
    if args.qsvm_samples and args.qsvm_samples < len(corpus):
        qb = [s for s in corpus if s[1] == 0][:args.qsvm_samples]
        qm = [s for s in corpus if s[1] == 1][:args.qsvm_samples]
        qsvm_corpus = qb + qm
        print(f"QSVM will train on a balanced subset: "
              f"{len(qb)} benign / {len(qm)} malicious")

    print(f"Training on {len(corpus)} samples "
          f"(counts may include duplicates)...")
    t0 = time.monotonic()

    pipeline = Pipeline(skip_train=True)
    pipeline._train_texts = corpus
    pipeline.train(qsvm_texts=qsvm_corpus)

    X_all = np.array([pipeline._vector(t) for t, _ in corpus], dtype=np.float64)
    y_all = np.array([l for _, l in corpus])
    scaled = pipeline.scaler.transform(X_all)

    async def _self_check() -> float:
        rf_pred = []
        for row in scaled.tolist():
            cls = (await pipeline.rf.predict(row))["predicted_class"]
            rf_pred.append(0 if cls == "benign" else 1)
        return float(np.mean([p == y for p, y in zip(rf_pred, y_all)]))

    acc = asyncio.run(_self_check())

    os.makedirs(args.state_dir, exist_ok=True)
    pipeline.save_state(args.state_dir)

    elapsed = time.monotonic() - t0
    print("-" * 60)
    print(f"Training finished in {elapsed:.1f}s")
    print(f"RandomForest self-check accuracy on the {len(corpus)} samples: "
          f"{acc * 100:.1f}%")
    print(f"Models saved to {args.state_dir}")
    print("Run `python scripts/prompt_cli.py` to use them.")


if __name__ == "__main__":
    main()
