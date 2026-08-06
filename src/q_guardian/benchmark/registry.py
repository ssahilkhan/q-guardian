"""Dataset registry for the QGuardian benchmark suite.

Defines ``DatasetSpec`` — the metadata + column-mapping contract that tells
the downloader, validator and preprocessor how to ingest a benchmark
dataset — and ``DatasetRegistry``, the catalog of datasets shipped with the
framework. Datasets are referenced by a stable ``dataset_id`` so benchmark
reports stay comparable across runs and releases.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class DatasetSpec:
    """Metadata describing a benchmark dataset and how to ingest it.

    A single spec encodes everything needed to download, validate and
    preprocess one dataset: source, format, splits, column mapping and
    licensing. Labels are resolved in order of precedence:

    1. ``label_field`` (optionally through ``label_map``) for explicit
       label columns,
    2. ``label_from_split`` for benchmarks whose label is implied by the
       split (e.g. JailbreakBench ``harmful`` / ``benign``),
    3. ``default_label`` for benign corpora.

    Args:
        dataset_id: Stable identifier used across reports and the registry.
        name: Human-readable dataset name.
        source: Hugging Face repo id (``owner/repo``) or a local file path.
        format: ``hf`` (Hugging Face datasets-server rows) or a local
            ``jsonl`` / ``csv`` / ``json`` file.
        config: Hugging Face config name, if any.
        splits: Split names to download (order is preserved).
        text_fields: Candidate text columns; the first non-empty wins.
        label_field: Column holding the label, if any.
        label_map: Optional raw-label → binary (0/1) mapping.
        label_from_split: Optional split → binary label mapping.
        default_label: Fallback label applied when no column/split label
            exists (used for benign corpora).
        category_field: Column holding the attack-category tag, if any.
        default_category: Category used when no category column exists.
        license: License of the dataset (or ``public``).
        homepage: Dataset homepage / repository URL.
        requires_token: Whether the source is gated on Hugging Face.
        max_samples: Optional cap on rows downloaded per split.
    """

    dataset_id: str
    name: str
    source: str
    format: str = "hf"
    config: str | None = None
    splits: tuple[str, ...] = ("default",)
    text_fields: tuple[str, ...] = ("text",)
    label_field: str | None = "label"
    label_map: dict[Any, int] | None = None
    label_from_split: dict[str, int] | None = None
    default_label: int | None = None
    category_field: str | None = None
    default_category: str = "benign"
    license: str = ""
    homepage: str = ""
    requires_token: bool = False
    max_samples: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the spec (for registry listings and reports)."""
        return asdict(self)


def _gated_spec(
    dataset_id: str,
    name: str,
    source: str,
    license_name: str,
    homepage: str,
) -> DatasetSpec:
    """Build a placeholder spec for a gated (token-required) dataset.

    Gated datasets can only be downloaded with a Hugging Face access token
    after accepting the dataset terms on the Hub. They are registered now
    so the catalog documents the full Phase 1 dataset set and downloads
    fail loudly without a token; their exact column mappings are finalized
    in M1b once authenticated access is available.
    """
    return DatasetSpec(
        dataset_id=dataset_id,
        name=name,
        source=source,
        format="hf",
        config=None,
        splits=("default",),
        text_fields=("text",),
        label_field=None,
        requires_token=True,
        license=license_name,
        homepage=homepage,
    )


_BUILTIN_SPECS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        dataset_id="deepset-prompt-injections",
        name="deepset/prompt-injections",
        source="deepset/prompt-injections",
        format="hf",
        config="default",
        splits=("train", "test"),
        text_fields=("text",),
        label_field="label",
        license="Apache-2.0",
        homepage="https://huggingface.co/datasets/deepset/prompt-injections",
        max_samples=2000,
    ),
    DatasetSpec(
        dataset_id="jbb-behaviors",
        name="JailbreakBench JBB-Behaviors",
        source="JailbreakBench/JBB-Behaviors",
        format="hf",
        config="behaviors",
        splits=("harmful", "benign"),
        text_fields=("Goal",),
        label_from_split={"harmful": 1, "benign": 0},
        category_field="Category",
        license="public",
        homepage="https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors",
    ),
    DatasetSpec(
        dataset_id="dolly-benign",
        name="databricks/databricks-dolly-15k (benign corpus)",
        source="databricks/databricks-dolly-15k",
        format="hf",
        config="default",
        splits=("train",),
        text_fields=("instruction",),
        default_label=0,
        category_field="category",
        license="CC BY-SA 3.0",
        homepage="https://huggingface.co/datasets/databricks/databricks-dolly-15k",
        max_samples=2000,
    ),
    _gated_spec(
        dataset_id="jailbreakbench-attacks",
        name="JailbreakBench JBB-Attacks (gated)",
        source="JailbreakBench/JBB-Attacks",
        license_name="public",
        homepage="https://huggingface.co/datasets/JailbreakBench/JBB-Attacks",
    ),
    _gated_spec(
        dataset_id="wildjailbreak",
        name="WildJailbreak (gated)",
        source="allenai/wildjailbreak",
        license_name="MIT",
        homepage="https://huggingface.co/datasets/allenai/wildjailbreak",
    ),
    _gated_spec(
        dataset_id="harmbench-behaviors",
        name="HarmBench Behaviors (gated)",
        source="cais/harmbench_behaviors",
        license_name="research-only",
        homepage="https://huggingface.co/datasets/cais/harmbench_behaviors",
    ),
    _gated_spec(
        dataset_id="advbench",
        name="AdvBench (gated)",
        source="DeepMind/AdvBench",
        license_name="research-only",
        homepage="https://huggingface.co/datasets/DeepMind/AdvBench",
    ),
    _gated_spec(
        dataset_id="hex-phi",
        name="HEx-PHI (gated)",
        source="walledai/HEx-PHI",
        license_name="research-only",
        homepage="https://huggingface.co/datasets/walledai/HEx-PHI",
    ),
    _gated_spec(
        dataset_id="pal",
        name="PAL — Protect AI (gated)",
        source="ProtectAI/PAL",
        license_name="research-only",
        homepage="https://huggingface.co/datasets/ProtectAI/PAL",
    ),
    _gated_spec(
        dataset_id="agentdojo",
        name="AgentDojo (gated)",
        source="ibm/agentdojo",
        license_name="CC BY 4.0",
        homepage="https://huggingface.co/datasets/ibm/agentdojo",
    ),
    _gated_spec(
        dataset_id="cyberseceval-prompt-injections",
        name="CyberSecEval Prompt Injections (gated)",
        source="facebook/CyberSecEval-PromptInjections",
        license_name="research-only",
        homepage="https://huggingface.co/datasets/facebook/CyberSecEval-PromptInjections",
    ),
)


class DatasetRegistry:
    """Catalog of benchmark datasets keyed by ``dataset_id``.

    Provides lookup, listing, and the public/gated split used to decide
    which datasets a token-less run can download.
    """

    def __init__(self, specs: Sequence[DatasetSpec] | None = None) -> None:
        if specs is None:
            specs = _BUILTIN_SPECS
        self._specs = {spec.dataset_id: spec for spec in specs}

    @classmethod
    def builtin(cls) -> DatasetRegistry:
        """Return the registry shipped with Q-Guardian."""
        return cls()

    def get(self, dataset_id: str) -> DatasetSpec:
        """Return the spec for ``dataset_id`` or raise ``KeyError``."""
        if dataset_id not in self._specs:
            msg = f"unknown dataset: {dataset_id}"
            raise KeyError(msg)
        return self._specs[dataset_id]

    def all(self) -> list[DatasetSpec]:
        """Return every spec, sorted by ``dataset_id``."""
        return [self._specs[key] for key in sorted(self._specs)]

    def public(self) -> list[DatasetSpec]:
        """Return specs downloadable without a Hugging Face token."""
        return [spec for spec in self.all() if not spec.requires_token]

    def gated(self) -> list[DatasetSpec]:
        """Return specs that require an access token (and accepted terms)."""
        return [spec for spec in self.all() if spec.requires_token]

    def public_ids(self) -> list[str]:
        """Return the ``dataset_id`` of every public spec."""
        return [spec.dataset_id for spec in self.public()]
