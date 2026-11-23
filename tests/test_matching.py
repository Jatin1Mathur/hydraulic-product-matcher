import numpy as np

from hpm.embeddings import HashingEmbedder, cosine
from hpm.matching import rank, score_candidate
from hpm.schemas import ComponentType, ProductSpec
from hpm.search import rrf

APP = ComponentType.AXIAL_PISTON_PUMP


def pump(model, disp, p=350, n=2600, circuit="open", mounting="SAE B", w=20.0):
    return ProductSpec(
        manufacturer="M",
        model=model,
        component_type=APP,
        circuit=circuit,
        mounting=mounting,
        displacement=disp,
        max_pressure=p,
        max_speed=n,
        weight=w,
    )


def valve(model, size, flow, p=350):
    return ProductSpec(
        manufacturer="M",
        model=model,
        component_type=ComponentType.DIRECTIONAL_VALVE,
        nominal_size=size,
        max_flow=flow,
        max_pressure=p,
        weight=1.5,
    )


def test_circuit_is_a_hard_rule():
    m = score_candidate(pump("C", 46, circuit="closed"), pump("R", 45, circuit="open"))
    assert not m.compatible
    assert any("circuit" in r for r in m.reasons_failed)


def test_pressure_rule_beats_closest_size():
    comp = pump("C", 19.5, p=275)
    refs = [pump("BIG", 22.5, p=250), pump("SMALL", 16, p=280)]
    assert rank(comp, refs, mode="naive")[0].reference.model == "BIG"
    best = rank(comp, refs, mode="rules")[0]
    assert best.reference.model == "SMALL" and best.compatible


def test_rating_within_tolerance_passes():
    m = score_candidate(pump("C", 25, n=3100), pump("R", 28, n=3000))
    speed = next(c for c in m.criteria if c.name == "max_speed")
    assert speed.passed and "tolerance" in speed.detail


def test_right_sizing_prefers_smaller_adequate_valve():
    comp = valve("C", "NG6", 79.5)
    ranked = rank(comp, [valve("HIGH", "NG6", 120), valve("STD", "NG6", 80)], mode="rules")
    assert [m.reference.model for m in ranked] == ["STD", "HIGH"]


def test_valve_interface_must_match():
    m = score_candidate(valve("C", "NG6", 60), valve("R", "NG10", 160))
    assert not m.compatible


def test_missing_value_is_flagged_not_failed():
    comp = pump("C", 45)
    comp.max_speed = None
    m = score_candidate(comp, pump("R", 45))
    speed = next(c for c in m.criteria if c.name == "max_speed")
    assert speed.passed is None and m.compatible


def test_other_component_types_are_never_candidates():
    ranked = rank(pump("C", 45), [pump("R", 45), valve("V", "NG6", 80)])
    assert [m.reference.model for m in ranked] == ["R"]


def test_rrf_rewards_agreement():
    fused = rrf({"vector": [1, 2, 3], "keyword": [3, 4, 1]})
    assert fused[0][0] in (1, 3) and {fused[0][0], fused[1][0]} == {1, 3}


def test_hashing_embedder_is_deterministic_and_normalised():
    e = HashingEmbedder(384)
    a, b = e.embed_documents(["load-sensing control", "load sensing control"])
    assert np.isclose(np.linalg.norm(a), 1.0)
    assert cosine(a, b) > 0.8
    assert np.allclose(e.embed_query("load-sensing control"), a)
