"""Angle encoding feature map — maps features to rotation gate angles."""

from __future__ import annotations

import math
from typing import Any

import structlog

from q_guardian.quantum.feature_maps.base import EncodedCircuit, QuantumFeatureMap
from q_guardian.quantum.enums import EncodingType
from q_guardian.quantum.config import QuantumFeatureMapConfig
from q_guardian.quantum.exceptions import EncodingDimensionError

logger = structlog.get_logger("quantum.angle_encoding")


class AngleEncodingMap(QuantumFeatureMap):
    """Angle encoding feature map.

    Encodes classical features as rotation angles on individual qubits.
    Each feature controls the rotation angle of one qubit.
    Supports Rx, Ry, and Rz rotation gates.

    For d features, requires ceil(d) qubits.
    Features outside the configured range are normalized.
    """

    def __init__(
        self,
        num_qubits: int = 5,
        config: QuantumFeatureMapConfig | None = None,
        rotation_gates: list[str] | None = None,
    ) -> None:
        self._config = config or QuantumFeatureMapConfig()
        self._num_qubits = num_qubits
        self._rotation_gates = rotation_gates or ["ry"]

    @property
    def name(self) -> str:
        return "angle-encoding"

    @property
    def encoding_type(self) -> EncodingType:
        return EncodingType.ANGLE

    @property
    def num_qubits(self) -> int:
        return self._num_qubits

    @property
    def rotation_gates(self) -> list[str]:
        return list(self._rotation_gates)

    def encode(self, features: list[float]) -> EncodedCircuit:
        if not features:
            msg = "Cannot encode empty feature vector"
            raise EncodingDimensionError(msg)

        normalized = self._normalize(features)
        n_qubits = min(len(normalized), self._num_qubits)
        circuit = self._build_circuit(normalized[:n_qubits], n_qubits)

        return EncodedCircuit(
            circuit=circuit,
            num_qubits=n_qubits,
            encoding_type=EncodingType.ANGLE,
            metadata={
                "feature_map": self.name,
                "rotation_gates": self._rotation_gates,
                "features_encoded": n_qubits,
                "features_dropped": max(0, len(features) - n_qubits),
            },
        )

    def validate_features(self, features: list[float]) -> bool:
        return len(features) > 0 and len(features) <= self._num_qubits * 10

    def _normalize(self, features: list[float]) -> list[float]:
        if not self._config.normalize_features:
            return features

        lo, hi = self._config.feature_range
        min_val = min(features) if features else 0.0
        max_val = max(features) if features else 1.0
        range_val = max_val - min_val

        if range_val == 0:
            mid = (lo + hi) / 2
            return [mid] * len(features)

        return [lo + (v - min_val) / range_val * (hi - lo) for v in features]

    def _build_circuit(self, features: list[float], num_qubits: int) -> dict[str, Any]:
        gates: list[dict[str, Any]] = []
        for i, angle in enumerate(features[:num_qubits]):
            gate = self._rotation_gates[i % len(self._rotation_gates)]
            gates.append({"type": gate, "qubits": [i], "params": [float(angle)]})

        return {
            "num_qubits": num_qubits,
            "gates": gates,
            "measurements": list(range(num_qubits)),
        }
