"""Explainable product matching: engineering rules + weighted spec score + semantic similarity.

For a competitor product, every reference product gets:
  1. hard rules     must pass, or the candidate is "not compatible" (still shown, with the reason)
  2. spec score     0..1, weighted closeness of each attribute
  3. semantic score 0..1, cosine similarity of the feature/control descriptions
  total = (1 - W_SEMANTIC) * spec + W_SEMANTIC * semantic

Every number in the result is traceable to one criterion with a human-readable detail,
so a product expert can see *why* a match was proposed and overrule it.
All thresholds and weights live in RULES / WEIGHTS below, in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hpm.schemas import ComponentType, ProductSpec

RULES = {
    "displacement_tolerance": 0.20,  # replacement within +-20 % of displacement
    "rating_tolerance": 0.05,  # pressure/speed/flow rating may be at most 5 % below the competitor's
}

WEIGHTS = {
    "pump": {"displacement": 0.45, "max_pressure": 0.20, "max_speed": 0.15, "mounting": 0.10, "weight": 0.10},
    "valve": {"max_flow": 0.45, "max_pressure": 0.35, "weight": 0.20},
}

W_SEMANTIC = 0.20


@dataclass
class Criterion:
    name: str
    score: float  # 0..1
    detail: str
    hard: bool = False
    passed: bool | None = True  # None = data missing, check manually


@dataclass
class MatchResult:
    reference: ProductSpec
    compatible: bool
    spec_score: float
    semantic_score: float
    total: float
    criteria: list[Criterion] = field(default_factory=list)

    @property
    def reasons_failed(self) -> list[str]:
        return [c.detail for c in self.criteria if c.hard and c.passed is False]


def _pct(a: float, b: float) -> str:
    return f"{(a - b) / b * 100:+.1f} %"


def _missing(name: str) -> Criterion:
    return Criterion(name, 0.5, f"{name}: value missing, check manually", passed=None)


def _closeness(name: str, comp: float | None, ref: float | None, tol: float, unit: str, hard: bool) -> Criterion:
    """Score how close ref is to comp; hard rule: within +-tol."""
    if comp is None or ref is None:
        return _missing(name)
    dev = abs(ref - comp) / comp
    ok = dev <= tol
    score = max(0.0, 1.0 - dev / tol)
    return Criterion(
        name, score, f"{name}: {ref:g} vs {comp:g} {unit} ({_pct(ref, comp)}, limit +-{tol:.0%})", hard=hard, passed=ok
    )


def _rating(name: str, comp: float | None, ref: float | None, tol: float, unit: str) -> Criterion:
    """Hard rule: the replacement's rating must not be more than tol below the competitor's."""
    if comp is None or ref is None:
        return _missing(name)
    ok = ref >= comp * (1 - tol)
    if ref >= comp:
        # Right-sizing: a much larger unit works but costs more and weighs more, so
        # oversizing is penalised mildly (score 0.75 at +50 %, never below 0.5).
        score, note = max(0.5, 1.0 - 0.5 * (ref - comp) / comp), "meets rating"
    elif ok:
        score, note = max(0.0, 1.0 - (comp - ref) / (comp * tol)), f"below rating, within {tol:.0%} tolerance"
    else:
        score, note = 0.0, f"below rating by more than {tol:.0%}"
    return Criterion(
        name, score, f"{name}: {ref:g} vs {comp:g} {unit} ({_pct(ref, comp)}, {note})", hard=True, passed=ok
    )


def _equal(
    name: str, comp: str | None, ref: str | None, hard: bool, soft_score: float = 0.0, soft_note: str = ""
) -> Criterion:
    if comp is None or ref is None:
        return _missing(name)
    if comp == ref:
        return Criterion(name, 1.0, f"{name}: {ref} = {comp}", hard=hard)
    return Criterion(name, soft_score, f"{name}: {ref} vs {comp}{soft_note}", hard=hard, passed=not hard)


def score_candidate(
    comp: ProductSpec, ref: ProductSpec, semantic: float = 0.0, use_rules: bool = True, use_semantic: bool = True
) -> MatchResult:
    tol_r = RULES["rating_tolerance"]
    crit: list[Criterion] = [_equal("component type", comp.component_type, ref.component_type, hard=True)]

    if comp.component_type.is_pump:
        weights = WEIGHTS["pump"]
        crit += [
            _equal("circuit", comp.circuit, ref.circuit, hard=True),
            _closeness(
                "displacement",
                comp.displacement,
                ref.displacement,
                RULES["displacement_tolerance"],
                "cm3/rev",
                hard=True,
            ),
            _rating("max_pressure", comp.max_pressure, ref.max_pressure, tol_r, "bar"),
            _rating("max_speed", comp.max_speed, ref.max_speed, tol_r, "rpm"),
            _equal(
                "mounting",
                comp.mounting,
                ref.mounting,
                hard=False,
                soft_score=0.5,
                soft_note=" (adapter flange needed)",
            ),
        ]
    else:
        weights = WEIGHTS["valve"]
        crit += [
            _equal("nominal_size", comp.nominal_size, ref.nominal_size, hard=True),
            _rating("max_flow", comp.max_flow, ref.max_flow, tol_r, "L/min"),
            _rating("max_pressure", comp.max_pressure, ref.max_pressure, tol_r, "bar"),
        ]
    if comp.weight is None or ref.weight is None:
        crit.append(_missing("weight"))
    else:
        dev = abs(ref.weight - comp.weight) / comp.weight
        crit.append(
            Criterion(
                "weight",
                max(0.0, 1.0 - dev),
                f"weight: {ref.weight:g} vs {comp.weight:g} kg ({_pct(ref.weight, comp.weight)})",
            )
        )

    by_name = {c.name: c for c in crit}
    spec = sum(weights[n] * by_name[n].score for n in weights if n in by_name) / sum(weights.values())
    compatible = (
        all(c.passed is not False for c in crit if c.hard) if use_rules else (comp.component_type == ref.component_type)
    )
    w_sem = W_SEMANTIC if use_semantic else 0.0
    total = (1 - w_sem) * spec + w_sem * semantic
    return MatchResult(ref, compatible, round(spec, 4), round(semantic, 4), round(total, 4), crit)


def rank(
    comp: ProductSpec, refs: list[ProductSpec], semantic: dict[str, float] | None = None, mode: str = "rules+semantic"
) -> list[MatchResult]:
    """Rank reference products for one competitor product.

    mode:
      naive           same type, closest displacement (pumps) / flow (valves). The baseline.
      rules           hard rules + spec score
      rules+semantic  hard rules + spec score + semantic similarity (default)
      semantic        same type, semantic similarity only
    """
    semantic = semantic or {}
    same_type = [r for r in refs if r.component_type == comp.component_type]

    if mode == "naive":
        key = "displacement" if comp.component_type.is_pump else "max_flow"
        target = getattr(comp, key) or 0.0

        def dist(r: ProductSpec) -> float:
            return abs((getattr(r, key) or 0.0) - target)

        return [score_candidate(comp, r, use_rules=False, use_semantic=False) for r in sorted(same_type, key=dist)]

    if mode == "semantic":
        results = [score_candidate(comp, r, semantic.get(r.model, 0.0), use_rules=False) for r in same_type]
        return sorted(results, key=lambda m: -m.semantic_score)

    use_sem = mode == "rules+semantic"
    results = [score_candidate(comp, r, semantic.get(r.model, 0.0), use_semantic=use_sem) for r in same_type]
    return sorted(results, key=lambda m: (not m.compatible, -m.total))


# Kept for type checkers: ComponentType is part of the public API of this module
__all__ = ["ComponentType", "Criterion", "MatchResult", "RULES", "WEIGHTS", "rank", "score_candidate"]
