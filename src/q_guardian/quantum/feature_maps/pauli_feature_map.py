"""Pauli feature map — rotation gates with Pauli entangling structure."""

from __future__ import annotations

import math
from typing import Any

from q_guardian.quantum.config import QuantumFeatureMapConfig
from q_guardian.quantum.enums import EncodingType
from q_guardian.quantum.exceptions import EncodingDimensionError
from q_guardian.quantum.feature_maps.base import EncodedCircuit, QuantumFeatureMap


class PauliFeatureMap(QuantumFeatureMap):
    """Pauli feature map using rotation gates and Pauli interactions.

    Each layer applies:
      1. Ry rotations for each qubit
      2. ZZ interaction between adjacent qubits (controlled-phase)
    """

    def __init__(
        self,
        num_qubits: int = 4,
        depth: int = 2,
        config: QuantumFeatureMapConfig | None = None,
    ) -> None:
        self._config = config or QuantumFeatureMapConfig()
        self._num_qubits = num_qubits
        self._depth = depth

    @property
    def name(self) -> str:
        return "pauli-feature-map"

    @property
    def encoding_type(self) -> EncodingType:
        return EncodingType.PAULI

    @property
    def num_qubits(self) -> int:
        return self._num_qubits

    @property
    def depth(self) -> int:
        return self._depth

    def encode(self, features: list[float]) -> EncodedCircuit:
        if not features:
            msg = "Cannot encode empty feature vector"
            raise EncodingDimensionError(msg)

        n_qubits = min(len(features), self._num_qubits)
        circuit = self._build_circuit(features[:n_qubits], n_qubits)

        return EncodedCircuit(
            circuit=circuit,
            num_qubits=n_qubits,
            encoding_type=EncodingType.PAULI,
            metadata={
                "feature_map": self.name,
                "depth": self._depth,
                "features_encoded": n_qubits,
            },
        )

    def _build_circuit(self, features: list[float], num_qubits: int) -> dict[str, Any]:
        gates: list[dict[str, Any]] = []

        for layer in range(self._depth):
            offset = layer * num_qubits
            for i in range(num_qubits):
                idx = (offset + i) % len(features)
                angle = features[idx] * math.pi
                gates.append({"type": "ry", "qubits": [i], "params": [float(angle)]})

            for i in range(num_qubits - 1):
                c, t = i, i + 1
                idx1 = (offset + c) % len(features)
                idx2 = (offset + t) % len(features)
                phase = features[idx1] * features[idx2] * math.pi
                gates.append({"type": "cz", "qubits": [c, t], "params": [float(phase)]})

        return {
            "num_qubits": num_qubits,
            "gates": gates,
            "measurements": list(range(num_qubits)),
        }
