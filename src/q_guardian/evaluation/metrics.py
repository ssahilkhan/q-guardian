"""Probability-based detection metrics for hybrid pipeline evaluation.

Provides threshold-based metrics (confusion matrix, precision, recall,
F1, MCC) as well as threshold-free and calibration metrics that require a
continuous threat score (ROC-AUC, PR-AUC, ECE, Brier). All metrics are
implemented in pure Python with no dependency on sklearn so they run in
any installation.
"""

from __future__ import annotations

from typing import Any


def _confusion(y_true: list[int], y_pred: list[int]) -> tuple[int, int, int, int]:
    """Return (tp, fp, fn, tn) for binary labels/predictions."""
    tp = fp = fn = tn = 0
    for t, p in zip(y_true, y_pred, strict=True):
        if p == 1:
            if t == 1:
                tp += 1
            else:
                fp += 1
        else:
            if t == 1:
                fn += 1
            else:
                tn += 1
    return tp, fp, fn, tn


def _binary_metrics(y_true: list[int], y_pred: list[int]) -> dict[str, Any]:
    """Compute threshold-based binary classification metrics."""
    tp, fp, fn, tn = _confusion(y_true, y_pred)
    total = len(y_true)
    accuracy = (tp + tn) / total if total > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    tpr = recall
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

    denom = (tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)
    mcc = (tp * tn - fp * fn) / (denom**0.5) if denom > 0 else 0.0

    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "specificity": specificity,
        "true_positive_rate": tpr,
        "false_positive_rate": fpr,
        "false_negative_rate": fnr,
        "matthews_corrcoef": mcc,
        "support": total,
        "positives": tp + fn,
        "negatives": fp + tn,
    }


def roc_auc(y_true: list[int], scores: list[float]) -> float:
    """Compute ROC-AUC via the Mann-Whitney U statistic with tie handling.

    A score of 0.5 means no better than random, 1.0 perfect ranking.
    """
    pairs = sorted(zip(scores, y_true, strict=True), key=lambda p: p[0])
    n = len(pairs)
    if n == 0:
        return 0.5

    ranks: list[float] = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1

    pos = sum(1 for _, t in pairs if t == 1)
    neg = n - pos
    if pos == 0 or neg == 0:
        return 0.5

    rank_sum_pos = sum(r for r, (_, t) in zip(ranks, pairs, strict=True) if t == 1)
    auc = (rank_sum_pos - pos * (pos + 1) / 2.0) / (pos * neg)
    return max(0.0, min(1.0, auc))


def pr_auc(y_true: list[int], scores: list[float]) -> float:
    """Compute area under the precision-recall curve.

    Precision is interpolated linearly between observed points; the curve
    starts at precision 1 / recall 0.
    """
    pairs = sorted(zip(scores, y_true, strict=True), key=lambda p: p[0], reverse=True)
    n_pos = sum(y_true)
    n_total = len(y_true)
    if n_total == 0:
        return 0.0
    if n_pos == 0:
        return 1.0
    if n_pos == n_total:
        return 1.0

    tp = 0
    fp = 0
    auc = 0.0
    prev_recall = 0.0
    prev_precision = 1.0
    for _score, t in pairs:
        if t == 1:
            tp += 1
        else:
            fp += 1
        recall = tp / n_pos
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        auc += (recall - prev_recall) * (precision + prev_precision) / 2.0
        prev_recall = recall
        prev_precision = precision
    return max(0.0, min(1.0, auc))


def expected_calibration_error(
    y_true: list[int],
    scores: list[float],
    n_bins: int = 10,
) -> float:
    """Compute the Expected Calibration Error.

    Scores are treated as predicted probabilities and binned; ECE is the
    mean absolute difference between accuracy and mean confidence within
    each bin, weighted by bin size. 0.0 is perfectly calibrated.
    """
    if not y_true:
        return 0.0
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for s, t in zip(scores, y_true, strict=True):
        clipped = max(0.0, min(1.0, float(s)))
        idx = min(int(clipped * n_bins), n_bins - 1)
        bins[idx].append((clipped, t))

    total = len(y_true)
    ece = 0.0
    for b in bins:
        if not b:
            continue
        conf = sum(s for s, _ in b) / len(b)
        acc = sum(t for _, t in b) / len(b)
        ece += (len(b) / total) * abs(acc - conf)
    return ece


def brier_score(y_true: list[int], scores: list[float]) -> float:
    """Compute the Brier score (mean squared error of predicted probability).

    Lower is better; 0.0 is a perfect forecast.
    """
    if not y_true:
        return 0.0
    return sum(
        (max(0.0, min(1.0, float(s))) - t) ** 2 for s, t in zip(scores, y_true, strict=True)
    ) / len(y_true)


def detection_metrics(
    y_true: list[int],
    scores: list[float],
    threshold: float = 0.5,
    n_bins: int = 10,
) -> dict[str, Any]:
    """Compute the full set of detection metrics for a threat score.

    Args:
        y_true: Binary ground-truth labels (1 = threat, 0 = benign).
        scores: Continuous threat scores per sample (higher = more threat).
        threshold: Decision threshold for the binary metrics.
        n_bins: Number of bins for ECE.

    Returns:
        Dictionary with threshold-based, threshold-free and calibration
        metrics plus the confusion matrix.
    """
    if len(y_true) != len(scores):
        msg = f"y_true ({len(y_true)}) and scores ({len(scores)}) length mismatch"
        raise ValueError(msg)

    y_pred = [1 if s >= threshold else 0 for s in scores]
    result = _binary_metrics(y_true, y_pred)
    result["confusion_matrix"] = _confusion(y_true, y_pred)
    result["threshold"] = threshold
    result["roc_auc"] = roc_auc(y_true, scores)
    result["pr_auc"] = pr_auc(y_true, scores)
    result["expected_calibration_error"] = expected_calibration_error(y_true, scores, n_bins=n_bins)
    result["brier_score"] = brier_score(y_true, scores)
    return result


class DetectionMetrics:
    """Namespace for detection metric computations."""

    confusion = staticmethod(_confusion)
    binary_metrics = staticmethod(_binary_metrics)
    roc_auc = staticmethod(roc_auc)
    pr_auc = staticmethod(pr_auc)
    expected_calibration_error = staticmethod(expected_calibration_error)
    brier = staticmethod(brier_score)
    compute = staticmethod(detection_metrics)
