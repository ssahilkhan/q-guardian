"""Dataset preparation: download -> normalize -> cap -> dedup -> split -> manifest.

This is the entry point of the dataset-preparation pipeline. It produces a
``PreparedDatasets`` object plus the reproducible run artifacts:

* ``dataset_manifest.json`` — per-dataset counts (requested/filtered/loaded/
  capped/deduplicated/leaked/final) and per-pool statistics
* ``leakage_report.json`` — training/evaluation contamination findings
* ``label_distribution.json`` — per-pool label + category counts
* ``splits/*.jsonl`` — the deterministic train/validation/test/external pools

Gated or unreachable datasets never break the pipeline when they are optional
(external evaluation). Required sources (train/validation) raise so a broken
training input cannot be silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from q_guardian.benchmark.download import DatasetDownloader, DatasetError
from q_guardian.benchmark.registry import DatasetRegistry
from q_guardian.training.artifacts import (
    label_distribution,
    write_json,
    write_splits,
)
from q_guardian.training.dedup import (
    DedupResult,
    LeakageReport,
    dedup_records,
    detect_leakage,
    remove_leaked,
)
from q_guardian.training.manifest import DatasetCounts, DatasetManifest
from q_guardian.training.normalize import DatasetRecordPreprocessor, count_raw_rows
from q_guardian.training.splitting import (
    assign_groups,
    cap_records,
    split_train_pool,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from q_guardian.training.config import TrainingPipelineConfig
    from q_guardian.training.schema import DatasetRecord

logger = structlog.get_logger("training.prepare")

POOL_NAMES = ("train", "validation", "test", "external_eval")


@dataclass
class PreparedDatasets:
    """Result of a preparation run, ready for training/evaluation."""

    config: TrainingPipelineConfig
    train: list[DatasetRecord]
    validation: list[DatasetRecord]
    test: list[DatasetRecord]
    external_eval: list[DatasetRecord]
    manifest: DatasetManifest
    leakage_report: LeakageReport
    output_dir: Path

    def splits(self) -> dict[str, list[DatasetRecord]]:
        return {
            "train": self.train,
            "validation": self.validation,
            "test": self.test,
            "external_eval": self.external_eval,
        }


class DatasetPreparationPipeline:
    """Orchestrates the full dataset-preparation pipeline.

    Args:
        registry: Dataset catalog (defaults to the built-in registry).
        downloader: Fetches dataset splits into a local cache.
        preprocessor: Maps raw rows onto canonical ``DatasetRecord``.
        progress: Optional callback receiving human-readable progress lines.
    """

    def __init__(
        self,
        *,
        registry: DatasetRegistry | None = None,
        downloader: DatasetDownloader | None = None,
        preprocessor: DatasetRecordPreprocessor | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self._registry = registry if registry is not None else DatasetRegistry.builtin()
        self._downloader = downloader if downloader is not None else DatasetDownloader()
        self._preprocessor = (
            preprocessor if preprocessor is not None else DatasetRecordPreprocessor()
        )
        self._progress = progress or (lambda msg: logger.info("prepare", msg=msg))

    def prepare(
        self,
        config: TrainingPipelineConfig,
        output_dir: str | Path | None = None,
        *,
        include_only: set[str] | None = None,
    ) -> PreparedDatasets:
        """Run the pipeline and persist artifacts under ``output_dir``.

        Args:
            config: Pipeline configuration.
            output_dir: Where run artifacts are written (defaults to
                ``config.output_dir``).
            include_only: Optional set of dataset ids to restrict processing
                to (e.g. from ``--datasets``).

        Raises:
            DatasetError: If a required (train/validation) source is
                unavailable.
            ValueError: If no usable training records remain.
        """
        run_dir = Path(output_dir) if output_dir is not None else config.output_dir
        source_ids = config.datasets.all_ids()
        if include_only is not None:
            source_ids = [dataset_id for dataset_id in source_ids if dataset_id in include_only]
            if not source_ids:
                msg = "--datasets filtered out every configured dataset"
                raise ValueError(msg)

        counts: dict[str, DatasetCounts] = {}
        all_records: list[DatasetRecord] = []
        for dataset_id in source_ids:
            dataset_counts, records = self._load_source(config, dataset_id)
            counts[dataset_id] = dataset_counts
            if not dataset_counts.available:
                self._report_unavailable(config, dataset_counts)
                continue
            all_records.extend(records)

        pools = assign_groups(all_records, config.datasets)
        train_pool, validation_pool = split_train_pool(
            pools["train"],
            config.datasets.validation,
            config.validation_ratio,
            config.seed,
        )

        dedup_result = dedup_records(train_pool, config.dedup)
        train = dedup_result.kept

        eval_splits: dict[str, list[DatasetRecord]] = {
            "validation": validation_pool,
            "test": pools["test"],
            "external_eval": pools["external_eval"],
        }
        leakage = detect_leakage(train, eval_splits, config.dedup)
        cleaned: dict[str, list[DatasetRecord]] = {}
        leaked_by_source: dict[str, int] = {}
        for name, records in eval_splits.items():
            kept, removed = remove_leaked(records, leakage.leaked_hashes(name))
            for record in removed:
                leaked_by_source[record.source] = leaked_by_source.get(record.source, 0) + 1
            cleaned[name] = kept

        validation = cleaned["validation"]
        test = cleaned["test"]
        external_eval = cleaned["external_eval"]

        if not train:
            msg = "no usable training records after preparation"
            raise ValueError(msg)

        self._finalize_counts(
            counts,
            dedup_result,
            leaked_by_source,
            {
                "train": train,
                "validation": validation,
                "test": test,
                "external_eval": external_eval,
            },
        )

        manifest = DatasetManifest.build(
            config,
            counts,
            {
                "train": train,
                "validation": validation,
                "test": test,
                "external_eval": external_eval,
            },
        )
        manifest.to_file(run_dir / "dataset_manifest.json")
        write_json(run_dir / "leakage_report.json", leakage.as_dict())
        write_json(
            run_dir / "label_distribution.json",
            {
                name: label_distribution(records)
                for name, records in {
                    "train": train,
                    "validation": validation,
                    "test": test,
                    "external_eval": external_eval,
                }.items()
            },
        )
        write_splits(
            run_dir,
            {
                "train": train,
                "validation": validation,
                "test": test,
                "external_eval": external_eval,
            },
        )

        self._log_summary(config, counts, train, validation, test, external_eval)
        return PreparedDatasets(
            config=config,
            train=train,
            validation=validation,
            test=test,
            external_eval=external_eval,
            manifest=manifest,
            leakage_report=leakage,
            output_dir=run_dir,
        )

    def _load_source(
        self,
        config: TrainingPipelineConfig,
        dataset_id: str,
    ) -> tuple[DatasetCounts, list[DatasetRecord]]:
        counts = DatasetCounts(source=dataset_id)
        try:
            spec = self._registry.get(dataset_id)
        except KeyError:
            counts.available = False
            counts.unavailable_reason = f"unknown dataset id: {dataset_id!r}"
            return counts, []
        self._progress(f"downloading {dataset_id}")
        try:
            split_paths = self._downloader.download(spec)
        except DatasetError as exc:
            counts.available = False
            counts.unavailable_reason = str(exc)
            return counts, []
        counts.requested = count_raw_rows(split_paths)
        records, filtered = self._preprocessor.preprocess(spec, split_paths)
        counts.filtered = filtered
        counts.loaded = len(records)
        cap = config.caps.get(dataset_id)
        kept, removed = cap_records(records, cap, config.seed)
        counts.capped = removed
        return counts, kept

    def _report_unavailable(self, config: TrainingPipelineConfig, counts: DatasetCounts) -> None:
        required = set(config.datasets.train) | set(config.datasets.validation)
        if counts.source in required:
            logger.error(
                "required_dataset_unavailable",
                dataset_id=counts.source,
                reason=counts.unavailable_reason,
            )
            raise DatasetError(
                f"required dataset {counts.source!r} is unavailable: {counts.unavailable_reason}"
            )
        logger.warning(
            "optional_dataset_unavailable",
            dataset_id=counts.source,
            reason=counts.unavailable_reason,
        )
        self._progress(
            f"WARNING: dataset {counts.source} unavailable — {counts.unavailable_reason}; "
            "continuing (optional external-evaluation source)"
        )

    @staticmethod
    def _finalize_counts(
        counts: dict[str, DatasetCounts],
        dedup_result: DedupResult,
        leaked_by_source: dict[str, int],
        pools: dict[str, list[DatasetRecord]],
    ) -> None:
        final_by_source: dict[str, int] = {}
        for records in pools.values():
            for record in records:
                final_by_source[record.source] = final_by_source.get(record.source, 0) + 1
        dedup_by_source: dict[str, int] = {}
        for removal in dedup_result.removed:
            dedup_by_source[removal.removed_source] = (
                dedup_by_source.get(removal.removed_source, 0) + 1
            )
        for dataset_id, dataset_counts in counts.items():
            dataset_counts.deduplicated = dedup_by_source.get(dataset_id, 0)
            dataset_counts.leaked = leaked_by_source.get(dataset_id, 0)
            dataset_counts.final = final_by_source.get(dataset_id, 0)

    @staticmethod
    def _log_summary(
        config: TrainingPipelineConfig,
        counts: dict[str, DatasetCounts],
        train: list[DatasetRecord],
        validation: list[DatasetRecord],
        test: list[DatasetRecord],
        external_eval: list[DatasetRecord],
    ) -> None:
        for dataset_id in config.datasets.all_ids():
            c = counts.get(dataset_id)
            if c is None:
                continue
            if c.available:
                logger.info(
                    "dataset_counts",
                    dataset_id=dataset_id,
                    requested=c.requested,
                    loaded=c.loaded,
                    filtered=c.filtered,
                    capped=c.capped,
                    deduplicated=c.deduplicated,
                    leaked=c.leaked,
                    final=c.final,
                )
            else:
                logger.warning(
                    "dataset_unavailable",
                    dataset_id=dataset_id,
                    reason=c.unavailable_reason,
                )
        logger.info(
            "prepared_pools",
            train=len(train),
            validation=len(validation),
            test=len(test),
            external_eval=len(external_eval),
        )
