"""ZZ Feature Map — entangling feature map for quantum kernels."""

from __future__ import annotations

import math
from typing import Any

import structlog

from q_guardian.quantum.config import QuantumFeatureMapConfig
from q_guardian.quantum.enums import EncodingType
from q_guardian.quantum.exceptions import EncodingDimensionError
from q_guardian.quantum.feature_maps.base import EncodedCircuit, QuantumFeatureMap

logger = structlog.get_logger("quantum.zz_feature_map")


class ZZFeatureMap(QuantumFeatureMap):
    """ZZ Feature Map for quantum kernel methods.

    Implements the data re-uploading strategy with entangling ZZ interactions.
    Creates expressible feature maps suitable for quantum kernel estimation.

    Circuit structure per layer:
      1. Single-qubit rotations Ry(features[i])
      2. ZZ entangling gates between adjacent qubits
      3. Repeat for depth layers
    """

    def __init__(
        self,
        num_qubits: int = 4,
        depth: int = 2,
        entanglement: str = "linear",
        config: QuantumFeatureMapConfig | None = None,
    ) -> None:
        self._config = config or QuantumFeatureMapConfig()
        self._num_qubits = num_qubits
        self._depth = depth
        self._entanglement = entanglement

    @property
    def name(self) -> str:
        return "zz-feature-map"

    @property
    def encoding_type(self) -> EncodingType:
        return EncodingType.ZZ_FEATURE_MAP

    @property
    def num_qubits(self) -> int:
        return self._num_qubits

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def entanglement(self) -> str:
        return self._entanglement

    def encode(self, features: list[float]) -> EncodedCircuit:
        if not features:
            msg = "Cannot encode empty feature vector"
            raise EncodingDimensionError(msg)

        n_qubits = min(len(features), self._num_qubits)
        circuit = self._build_circuit(features[:n_qubits], n_qubits)

        return EncodedCircuit(
            circuit=circuit,
            num_qubits=n_qubits,
            encoding_type=EncodingType.ZZ_FEATURE_MAP,
            metadata={
                "feature_map": self.name,
                "depth": self._depth,
                "entanglement": self._entanglement,
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

            pairs = self._get_entangling_pairs(num_qubits)
            for c, t in pairs:
                gates.append({"type": "cz", "qubits": [c, t], "params": []})

        measurements = list(range(num_qubits))
        return {
            "num_qubits": num_qubits,
            "gates": gates,
            "measurements": measurements,
        }

    def _get_entangling_pairs(self, num_qubits: int) -> list[tuple[int, int]]:
        if self._entanglement == "linear":
            return [(i, i + 1) for i in range(num_qubits - 1)]
        elif self._entanglement == "circular":
            pairs = [(i, i + 1) for i in range(num_qubits - 1)]
            if num_qubits > 2:
                pairs.append((num_qubits - 1, 0))
            return pairs
        elif self._entanglement == "full":
            return [(i, j) for i in range(num_qubits) for j in range(i + 1, num_qubits)]
        return [(i, i + 1) for i in range(num_qubits - 1)]
