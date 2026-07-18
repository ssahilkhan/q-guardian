"""Evaluation and benchmarking metrics for ML models."""

from __future__ import annotations

from typing import Any

from q_guardian.ml.data import EvaluationMetrics


class BenchmarkMetrics:
    """Standard ML benchmarking metrics.

    Computes accuracy, precision, recall, F1, AUC-ROC,
    confusion matrix, and per-class metrics.
    """

    def compute_classification_metrics(
        self,
        y_true: list[int],
        y_pred: list[int],
        class_names: list[str] | None = None,
    ) -> EvaluationMetrics:
        """Compute classification metrics.

        Args:
            y_true: Ground truth labels.
            y_pred: Predicted labels.
            class_names: Optional class names for per-class metrics.

        Returns:
            EvaluationMetrics with all computed metrics.
        """
        if not y_true or not y_pred:
            return EvaluationMetrics()

        tp = sum(1 for t, p in zip(y_true, y_pred) if t == p and t == 1)
        tn = sum(1 for t, p in zip(y_true, y_pred) if t == p and t == 0)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != p and p == 1)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t != p and p == 0)

        total = len(y_true)
        accuracy = (tp + tn) / total if total > 0 else 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        # AUC-ROC approximation for binary case
        auc_roc = self._approximate_auc_roc(y_true, y_pred)

        # Confusion matrix
        labels = sorted(set(y_true) | set(y_pred))
        n_labels = max(len(labels), max(labels) + 1 if labels else 2)
        matrix = [[0] * n_labels for _ in range(n_labels)]
        for t, p in zip(y_true, y_pred):
            matrix[t][p] += 1

        # Per-class metrics
        per_class: dict[str, dict[str, float]] = {}
        for label in labels:
            label_tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
            label_fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
            label_fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)

            l_precision = label_tp / (label_tp + label_fp) if (label_tp + label_fp) > 0 else 0.0
            l_recall = label_tp / (label_tp + label_fn) if (label_tp + label_fn) > 0 else 0.0
            l_f1 = (
                2 * l_precision * l_recall / (l_precision + l_recall)
                if (l_precision + l_recall) > 0
                else 0.0
            )

            name = class_names[label] if class_names and label < len(class_names) else str(label)
            per_class[name] = {
                "precision": l_precision,
                "recall": l_recall,
                "f1_score": l_f1,
                "support": float(sum(1 for t in y_true if t == label)),
            }

        return EvaluationMetrics(
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1,
            auc_roc=auc_roc,
            true_positives=tp,
            true_negatives=tn,
            false_positives=fp,
            false_negatives=fn,
            confusion_matrix=matrix,
            per_class_metrics=per_class,
        )

    def _approximate_auc_roc(
        self, y_true: list[int], y_pred: list[int]
    ) -> float:
        """Simple AUC-ROC approximation from binary predictions."""
        if not y_true:
            return 0.0

        # For hard predictions, approximate with balanced accuracy
        pos_true = [i for i, v in enumerate(y_true) if v == 1]
        neg_true = [i for i, v in enumerate(y_true) if v == 0]

        tpr = sum(1 for i in pos_true if y_pred[i] == 1) / max(len(pos_true), 1)
        fpr = sum(1 for i in neg_true if y_pred[i] == 1) / max(len(neg_true), 1)

        return max(0.0, min(1.0, (tpr + (1 - fpr)) / 2))

    def compute_anomaly_metrics(
        self,
        y_true_anomaly: list[bool],
        y_pred_anomaly: list[bool],
    ) -> dict[str, float]:
        """Compute anomaly detection metrics.

        Args:
            y_true_anomaly: Ground truth anomaly flags.
            y_pred_anomaly: Predicted anomaly flags.

        Returns:
            Dictionary with detection rate, false positive rate, etc.
        """
        if not y_true_anomaly:
            return {}

        tp = sum(1 for t, p in zip(y_true_anomaly, y_pred_anomaly) if t and p)
        fp = sum(1 for t, p in zip(y_true_anomaly, y_pred_anomaly) if not t and p)
        fn = sum(1 for t, p in zip(y_true_anomaly, y_pred_anomaly) if t and not p)
        tn = sum(1 for t, p in zip(y_true_anomaly, y_pred_anomaly) if not t and not p)

        total = len(y_true_anomaly)
        detection_rate = tp / max(sum(y_true_anomaly), 1)
        false_positive_rate = fp / max(sum(not t for t in y_true_anomaly), 1)
        accuracy = (tp + tn) / total if total > 0 else 0.0

        return {
            "detection_rate": detection_rate,
            "false_positive_rate": false_positive_rate,
            "accuracy": accuracy,
            "true_positives": float(tp),
            "true_negatives": float(tn),
            "false_positives": float(fp),
            "false_negatives": float(fn),
        }


class ResearchMetrics:
    """Extended metrics for research and comparison."""

    def compute_prompt_security_metrics(
        self,
        y_true_labels: list[str],
        y_pred_labels: list[str],
        y_true_severity: list[str] | None = None,
        y_pred_severity: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compute prompt-security-specific metrics.

        Includes severity-weighted accuracy and category-level F1.
        """
        benchmark = BenchmarkMetrics()

        # Map labels to integers for standard metrics
        all_labels = sorted(set(y_true_labels) | set(y_pred_labels))
        label_map = {label: i for i, label in enumerate(all_labels)}
        y_true_int = [label_map[l] for l in y_true_labels]
        y_pred_int = [label_map[l] for l in y_pred_labels]

        base_metrics = benchmark.compute_classification_metrics(
            y_true_int, y_pred_int, class_names=all_labels
        )

        result: dict[str, Any] = base_metrics.model_dump()

        # Severity-weighted accuracy
        if y_true_severity and y_pred_severity:
            severity_weights = {
                "info": 0.1, "low": 0.2, "medium": 0.5,
                "high": 0.8, "critical": 1.0,
            }
            weighted_correct = 0.0
            total_weight = 0.0
            for t, p, s in zip(y_true_labels, y_pred_labels, y_true_severity):
                w = severity_weights.get(s, 0.5)
                total_weight += w
                if t == p:
                    weighted_correct += w

            result["severity_weighted_accuracy"] = (
                weighted_correct / max(total_weight, 1e-10)
            )

        return result
