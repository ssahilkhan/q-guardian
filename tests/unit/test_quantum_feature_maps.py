"""Tests for quantum feature maps — Angle, ZZ, Pauli."""

from __future__ import annotations

import pytest

from q_guardian.quantum.config import QuantumFeatureMapConfig
from q_guardian.quantum.enums import EncodingType
from q_guardian.quantum.exceptions import EncodingDimensionError
from q_guardian.quantum.feature_maps.angle_encoding import AngleEncodingMap
from q_guardian.quantum.feature_maps.base import EncodedCircuit, QuantumFeatureMap
from q_guardian.quantum.feature_maps.pauli_feature_map import PauliFeatureMap
from q_guardian.quantum.feature_maps.zz_feature_map import ZZFeatureMap


class DummyFeatureMap(QuantumFeatureMap):
    """Minimal concrete feature map for testing ABC contract."""

    @property
    def name(self) -> str:
        return "dummy-map"

    @property
    def encoding_type(self) -> EncodingType:
        return EncodingType.ANGLE

    @property
    def num_qubits(self) -> int:
        return 4

    def encode(self, features: list[float]) -> EncodedCircuit:
        return EncodedCircuit(
            circuit={"num_qubits": len(features), "gates": [], "measurements": []},
            num_qubits=len(features),
            encoding_type=EncodingType.ANGLE,
        )


class TestQuantumFeatureMapABC:
    def test_interface_contract(self) -> None:
        fm = DummyFeatureMap()
        assert fm.name == "dummy-map"
        assert fm.encoding_type == EncodingType.ANGLE
        assert fm.num_qubits == 4

    def test_encode(self) -> None:
        fm = DummyFeatureMap()
        result = fm.encode([1.0, 2.0, 3.0])
        assert isinstance(result, EncodedCircuit)
        assert result.num_qubits == 3

    def test_encode_batch(self) -> None:
        fm = DummyFeatureMap()
        batch = [[1.0, 2.0], [3.0, 4.0]]
        results = fm.encode_batch(batch)
        assert len(results) == 2

    def test_validate_features(self) -> None:
        fm = DummyFeatureMap()
        assert fm.validate_features([1.0, 2.0]) is True
        assert fm.validate_features([]) is False

    def test_health(self) -> None:
        fm = DummyFeatureMap()
        h = fm.health()
        assert h["status"] == "healthy"
        assert h["feature_map"] == "dummy-map"


class TestAngleEncodingMap:
    def setup_method(self) -> None:
        self.fm = AngleEncodingMap(num_qubits=5)

    def test_name(self) -> None:
        assert self.fm.name == "angle-encoding"

    def test_encoding_type(self) -> None:
        assert self.fm.encoding_type == EncodingType.ANGLE

    def test_num_qubits(self) -> None:
        assert self.fm.num_qubits == 5

    def test_encode_basic(self) -> None:
        result = self.fm.encode([0.5, 1.0, 1.5])
        assert result.num_qubits == 3
        assert result.encoding_type == EncodingType.ANGLE
        assert len(result.circuit["gates"]) == 3

    def test_encode_exact_qubits(self) -> None:
        result = self.fm.encode([0.1, 0.2, 0.3, 0.4, 0.5])
        assert result.num_qubits == 5

    def test_encode_more_features_than_qubits(self) -> None:
        result = self.fm.encode([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
        assert result.num_qubits == 5

    def test_encode_empty_raises(self) -> None:
        with pytest.raises(EncodingDimensionError):
            self.fm.encode([])

    def test_encode_normalization(self) -> None:
        result = self.fm.encode([10.0, 20.0, 30.0])
        assert result.num_qubits == 3
        gates = result.circuit["gates"]
        for gate in gates:
            assert gate["type"] == "ry"

    def test_encode_different_rotation_gates(self) -> None:
        fm = AngleEncodingMap(num_qubits=3, rotation_gates=["rx", "ry", "rz"])
        result = fm.encode([0.5, 1.0, 1.5])
        gates = result.circuit["gates"]
        assert gates[0]["type"] == "rx"
        assert gates[1]["type"] == "ry"
        assert gates[2]["type"] == "rz"

    def test_encode_with_config(self) -> None:
        config = QuantumFeatureMapConfig(
            normalize_features=False,
            feature_range=(0.0, 6.28),
        )
        fm = AngleEncodingMap(num_qubits=3, config=config)
        result = fm.encode([0.5, 1.0, 1.5])
        assert result.num_qubits == 3

    def test_validate_features(self) -> None:
        assert self.fm.validate_features([1.0, 2.0, 3.0]) is True
        assert self.fm.validate_features([]) is False

    def test_encode_metadata(self) -> None:
        result = self.fm.encode([0.5, 1.0])
        assert "feature_map" in result.metadata
        assert result.metadata["features_encoded"] == 2

    def test_encode_single_feature(self) -> None:
        result = self.fm.encode([1.5])
        assert result.num_qubits == 1
        assert len(result.circuit["gates"]) == 1


class TestZZFeatureMap:
    def setup_method(self) -> None:
        self.fm = ZZFeatureMap(num_qubits=4, depth=2)

    def test_name(self) -> None:
        assert self.fm.name == "zz-feature-map"

    def test_encoding_type(self) -> None:
        assert self.fm.encoding_type == EncodingType.ZZ_FEATURE_MAP

    def test_num_qubits(self) -> None:
        assert self.fm.num_qubits == 4

    def test_depth(self) -> None:
        assert self.fm.depth == 2

    def test_encode_basic(self) -> None:
        result = self.fm.encode([0.5, 1.0, 1.5, 2.0])
        assert result.num_qubits == 4
        assert result.encoding_type == EncodingType.ZZ_FEATURE_MAP
        gates = result.circuit["gates"]
        assert len(gates) > 0

    def test_encode_empty_raises(self) -> None:
        with pytest.raises(EncodingDimensionError):
            self.fm.encode([])

    def test_linear_entanglement(self) -> None:
        fm = ZZFeatureMap(num_qubits=4, entanglement="linear")
        result = fm.encode([0.5, 1.0, 1.5, 2.0])
        gate_types = [g["type"] for g in result.circuit["gates"]]
        assert "cz" in gate_types

    def test_circular_entanglement(self) -> None:
        fm = ZZFeatureMap(num_qubits=4, entanglement="circular")
        result = fm.encode([0.5, 1.0, 1.5, 2.0])
        gate_types = [g["type"] for g in result.circuit["gates"]]
        assert "cz" in gate_types

    def test_full_entanglement(self) -> None:
        fm = ZZFeatureMap(num_qubits=3, entanglement="full")
        result = fm.encode([0.5, 1.0, 1.5])
        cz_count = sum(1 for g in result.circuit["gates"] if g["type"] == "cz")
        assert cz_count >= 3

    def test_depth_1(self) -> None:
        fm = ZZFeatureMap(num_qubits=3, depth=1)
        result = fm.encode([0.5, 1.0, 1.5])
        assert result.metadata["depth"] == 1

    def test_circuit_structure(self) -> None:
        result = self.fm.encode([0.5, 1.0, 1.5, 2.0])
        circuit = result.circuit
        assert "num_qubits" in circuit
        assert "gates" in circuit
        assert "measurements" in circuit
        assert circuit["num_qubits"] == 4

    def test_encode_more_features(self) -> None:
        result = self.fm.encode([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
        assert result.num_qubits == 4


class TestPauliFeatureMap:
    def setup_method(self) -> None:
        self.fm = PauliFeatureMap(num_qubits=3, depth=2)

    def test_name(self) -> None:
        assert self.fm.name == "pauli-feature-map"

    def test_encoding_type(self) -> None:
        assert self.fm.encoding_type == EncodingType.PAULI

    def test_num_qubits(self) -> None:
        assert self.fm.num_qubits == 3

    def test_encode_basic(self) -> None:
        result = self.fm.encode([0.5, 1.0, 1.5])
        assert result.num_qubits == 3
        assert result.encoding_type == EncodingType.PAULI

    def test_encode_empty_raises(self) -> None:
        with pytest.raises(EncodingDimensionError):
            self.fm.encode([])

    def test_circuit_has_ry_and_cz(self) -> None:
        result = self.fm.encode([0.5, 1.0, 1.5])
        gate_types = [g["type"] for g in result.circuit["gates"]]
        assert "ry" in gate_types
        assert "cz" in gate_types

    def test_depth_impacts_gates(self) -> None:
        fm1 = PauliFeatureMap(num_qubits=3, depth=1)
        fm2 = PauliFeatureMap(num_qubits=3, depth=3)
        r1 = fm1.encode([0.5, 1.0, 1.5])
        r2 = fm2.encode([0.5, 1.0, 1.5])
        assert len(r2.circuit["gates"]) > len(r1.circuit["gates"])

    def test_measurements(self) -> None:
        result = self.fm.encode([0.5, 1.0, 1.5])
        assert result.circuit["measurements"] == [0, 1, 2]
