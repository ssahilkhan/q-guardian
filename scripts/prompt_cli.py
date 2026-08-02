"""Interactive Q-Guardian prompt tester with persistent memory + learning.

Type any prompt and the framework analyzes it end-to-end (features, ML,
quantum QSVM, fusion, risk, policy, response) with full backend detail.

Every prompt is recorded to disk. Use `:label` to correct the auto-assigned
label (benign/malicious) and `:learn` to retrain all models on everything it
has seen so far, so it genuinely learns from what you feed it across sessions.

Usage:
    python scripts/prompt_cli.py                 # interactive REPL (clean verdict)
    python scripts/prompt_cli.py "my prompt"     # single-shot, clean verdict
    python scripts/prompt_cli.py --verbose "my prompt"  # full backend detail
    python scripts/prompt_cli.py --forget        # wipe memory + saved models

REPL commands:
    <prompt>   analyze the prompt through the full pipeline
    :simple    toggle clean verdict output vs full backend detail
    :label     correct the label of the last analyzed prompt
    :learn     retrain all models from memory (persists state)
    :memory    show what the framework remembers so far
    :forget    erase all memory and saved models
    :quit      save + exit (Ctrl+C also works)
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
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

import numpy as np
import sklearn  # noqa: F401  (imported for bundled-sklearn detection)

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "examples" / "prompt_test_harness.py"
MEMORY_FILE = ROOT / "examples" / "qg_memory.jsonl"
STATE_DIR = ROOT / "examples" / "qg_state"
STATE_DIR_OVERRIDE = None

_spec = importlib.util.spec_from_file_location("prompt_test_harness", HARNESS)
assert _spec is not None and _spec.loader is not None, "harness import failed"
HARNESS_MOD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(HARNESS_MOD)
Pipeline = HARNESS_MOD.Pipeline


# ----------------------------------------------------------------------
# Memory (persistent JSONL)
# ----------------------------------------------------------------------
def load_memory(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def append_memory(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def rewrite_memory(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def auto_label(action: str) -> int:
    return 0 if action.upper() == "ALLOW" else 1


def verdict_for(action: str) -> str:
    a = action.upper()
    if a in ("ALLOW", "LOG_ONLY"):
        return "SAFE"
    if a in ("WARN", "REVIEW", "MONITOR"):
        return "SUSPICIOUS"
    return "UNSAFE"


def print_verdict(result: dict) -> None:
    """Compact, readable verdict with per-path numeric breakdown."""
    v = verdict_for(result["action"])
    probs = result.get("fused", {})
    breakdown = result.get("path_breakdown", {})
    path_groups: dict[str, list] = {}
    for pid, b in breakdown.items():
        if pid in ("isolation-forest", "random-forest"):
            group = "Classical ML"
        elif pid == "qsvm":
            group = "Quantum QSVM"
        else:
            group = "Rules"
        path_groups.setdefault(group, []).append((pid, b))

    def _line(pid: str, b: dict) -> str:
        p = b.get("probabilities", {})
        safe = p.get("benign", 0.0) * 100
        mall = p.get("threat", 0.0) * 100
        return (f"    {pid:<16} safe {safe:5.1f}% | "
                f"malicious {mall:5.1f}%   risk {b['risk_score']:.2f}")

    print("=" * 64)
    print(f"  VERDICT: {v}  ->  {result['action']}")
    print("=" * 64)

    for group_name, items in path_groups.items():
        print(f"  -- {group_name} --")
        for pid, b in items:
            print(_line(pid, b))
        if items:
            mean = sum(b["probabilities"].get("threat", 0.0)
                       for _, b in items) / len(items)
            print(f"    combined malicious confidence: {mean * 100:.1f}%")

    print("  -- Hybrid fusion (weighted voting) --")
    print("    fused label :", result["fused_label"],
          f"(confidence {result['confidence']:.3f})")
    prob_str = " | ".join(f"{k} {v2:.1f}%" for k, v2 in probs.items())
    print(f"    class probs : {prob_str}")

    print("  -- Final output --")
    print(f"    verdict     : {v}")
    print(f"    action      : {result['action']}")
    print(f"    risk level  : {result['risk_level']}")
    print(f"    risk score  : {result['risk_score']:.4f}")
    rules = result.get("rules", [])
    rules_str = ", ".join(f"{r[0]}" for r in rules) or "none"
    print(f"    rules fired : {rules_str}")


# ----------------------------------------------------------------------
def main() -> None:
    args = sys.argv[1:]

    global STATE_DIR
    if "--state-dir" in args:
        i = args.index("--state-dir")
        STATE_DIR = Path(args[i + 1])
        del args[i:i + 2]

    if "--forget" in args:
        if MEMORY_FILE.exists():
            MEMORY_FILE.unlink()
        if STATE_DIR.exists():
            import shutil
            shutil.rmtree(STATE_DIR)
        print("Memory and saved models erased.")
        return

    memory = load_memory(MEMORY_FILE)

    simple_mode = "--verbose" not in args

    t0 = time.monotonic()
    print("Initializing Q-Guardian pipeline...")
    pipeline = Pipeline(skip_train=True)
    if STATE_DIR.exists():
        pipeline.load_state(str(STATE_DIR))
    else:
        for rec in memory:
            if rec.get("label") is not None:
                pipeline.add_sample(rec["text"], int(rec["label"]))
        pipeline.train()
        pipeline.save_state(str(STATE_DIR))
    print(f"Pipeline ready in {(time.monotonic() - t0) * 1000:.0f} ms "
          f"| memory: {len(memory)} prompts")

    last_record: dict | None = None

    def analyze(prompt: str) -> None:
        nonlocal last_record
        if simple_mode:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                result = pipeline.run(prompt)
            print_verdict(result)
        else:
            result = pipeline.run(prompt)
        label = auto_label(result["action"])
        record = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "text": prompt,
            "label": label,
            "auto": True,
            "action": result["action"],
            "risk_level": result["risk_level"],
            "risk_score": round(float(result["risk_score"]), 4),
        }
        append_memory(MEMORY_FILE, record)
        memory.append(record)
        last_record = record
        print(f"  [recorded -> {'malicious' if label else 'benign'} "
              f"(auto), run :label to correct, :learn to retrain]")

    def cmd_label() -> None:
        nonlocal last_record
        if last_record is None:
            print("  No prompt analyzed yet.")
            return
        answer = input("  Is this prompt [b]enign or [m]alicious? (b/m): ").strip().lower()
        if answer not in ("b", "m"):
            print("  Ignored (expected b or m).")
            return
        new_label = 0 if answer == "b" else 1
        last_record["label"] = new_label
        last_record["auto"] = False
        rewrite_memory(MEMORY_FILE, memory)
        print(f"  Label updated to {'malicious' if new_label else 'benign'} "
              f"for: {last_record['text'][:60]}")
        print("  Run :learn to incorporate this into the models.")

    def cmd_learn() -> None:
        nonlocal last_record
        labeled = [r for r in memory if r.get("label") is not None]
        if not labeled:
            print("  Nothing to learn from yet (analyze some prompts first).")
            return
        print(f"  Retraining on {len(labeled)} remembered prompts + defaults...")
        base = [(t, 0) for t in HARNESS_MOD._TRAIN_BENIGN] + \
               [(t, 1) for t in HARNESS_MOD._TRAIN_MALICIOUS]
        pipeline._train_texts = base + [(r["text"], int(r["label"])) for r in labeled]
        pipeline.train()
        pipeline.save_state(str(STATE_DIR))
        print("  Done. Models now trained on everything it has seen.")

    def cmd_memory() -> None:
        labeled = [r for r in memory if r.get("label") is not None]
        benign = sum(1 for r in labeled if r["label"] == 0)
        malicious = sum(1 for r in labeled if r["label"] == 1)
        print(f"  memory: {len(memory)} prompts "
              f"({len(labeled)} labeled: {benign} benign / {malicious} malicious)")
        for r in memory[-10:]:
            flag = "B" if r.get("label") == 0 else "M" if r.get("label") == 1 else "?"
            auto = "auto" if r.get("auto") else "user"
            print(f"    [{flag}/{auto}] {r['text'][:70]} -> "
                  f"{r['action']} ({r['risk_level']}, {r['risk_score']})")

    single = [a for a in args if not a.startswith("--") and a != "-s"]
    if single:
        for prompt in single:
            analyze(prompt)
        pipeline.save_state(str(STATE_DIR))
        return

    print("-" * 88)
    print("Interactive Q-Guardian tester. Type a prompt to analyze it.")
    print("Commands: :simple  :label  :learn  :memory  :forget  :quit")
    print("-" * 88)

    while True:
        try:
            line = input("\nprompt> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break
        if not line:
            continue
        if line.startswith(":"):
            cmd = line[1:].strip().lower()
            if cmd in ("quit", "exit", "q"):
                print("Bye.")
                break
            elif cmd in ("simple", "verbose"):
                simple_mode = not simple_mode
                print(f"  Output mode: "
                      f"{'clean verdict' if simple_mode else 'full backend detail'}")
            elif cmd == "label":
                cmd_label()
            elif cmd == "learn":
                cmd_learn()
            elif cmd == "memory":
                cmd_memory()
            elif cmd == "forget":
                print("  Use `python scripts/prompt_cli.py --forget` outside the REPL.")
            else:
                print(f"  Unknown command: {line}")
        else:
            analyze(line)

    if STATE_DIR.exists():
        pipeline.save_state(str(STATE_DIR))


if __name__ == "__main__":
    main()
