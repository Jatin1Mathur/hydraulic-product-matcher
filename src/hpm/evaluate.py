"""Evaluation against the labelled ground truth.

  1. Extraction accuracy  every extracted field vs the true value (numbers within 2 %,
                          because catalogues print rounded figures in their own units)
  2. Matching             top-1 accuracy, top-3 accuracy and MRR for each matching mode,
                          plus how many of the hard cases each mode gets right
  3. Retrieval            hit@3 of vector, keyword and hybrid search on labelled questions

Writes reports/eval.md and reports/eval.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from hpm import service
from hpm.config import settings
from hpm.db import make_engine, make_session_factory
from hpm.embeddings import make_embedder
from hpm.search import search

ROOT = Path(__file__).resolve().parents[2]
FIELD_MAP = {"type": "component_type", "size": "nominal_size"}
MODES = ["naive", "semantic", "rules", "rules+semantic"]


def _close(got, want) -> bool:
    if isinstance(want, int | float) and not isinstance(want, bool):
        return got is not None and abs(got - want) / abs(want) <= 0.02
    return got is not None and str(got) == str(want)


def eval_extraction(session, truth: dict) -> dict:
    per_field: dict[str, list[int]] = {}
    errors = []
    for model, t in truth["products"].items():
        p = service.get_product(session, model)
        for key, want in t.items():
            if key == "brand":
                continue
            got = getattr(p, FIELD_MAP.get(key, key)) if p else None
            ok = _close(got, want)
            per_field.setdefault(key, [0, 0])
            per_field[key][0] += ok
            per_field[key][1] += 1
            if not ok:
                errors.append(f"{model}.{key}: expected {want}, got {got}")
    correct = sum(v[0] for v in per_field.values())
    total = sum(v[1] for v in per_field.values())
    return {
        "accuracy": correct / total,
        "correct": correct,
        "total": total,
        "per_field": {k: v[0] / v[1] for k, v in per_field.items()},
        "errors": errors,
    }


def eval_matching(session, truth: dict) -> dict:
    out = {}
    hard = set(truth["hard_cases"])
    for mode in MODES:
        top1 = top3 = 0
        rr = 0.0
        hard_ok = 0
        misses = []
        for comp, expected in truth["matches"].items():
            ranked = [m.reference.model for m in service.match(session, comp, mode=mode, top_k=20)]
            rank = ranked.index(expected) + 1 if expected in ranked else None
            top1 += rank == 1
            top3 += rank is not None and rank <= 3
            rr += 1 / rank if rank else 0.0
            if comp in hard and rank == 1:
                hard_ok += 1
            if rank != 1:
                misses.append(f"{comp}: expected {expected}, got {ranked[0] if ranked else None}")
        n = len(truth["matches"])
        out[mode] = {
            "top1": top1 / n,
            "top3": top3 / n,
            "mrr": rr / n,
            "hard_cases": f"{hard_ok}/{len(hard)}",
            "n": n,
            "misses": misses,
        }
    return out


def eval_retrieval(session, embedder, questions: list[dict]) -> dict:
    out = {}
    for mode in ["vector", "keyword", "hybrid"]:
        hits = 0
        for q in questions:
            docs = [h.filename for h in search(session, embedder, q["question"], k=3, mode=mode)]
            hits += any(d in docs for d in q["expected_docs"])
        out[mode] = {"hit@3": hits / len(questions), "n": len(questions)}
    return out


def to_markdown(r: dict) -> str:
    ex, ma, re_ = r["extraction"], r["matching"], r["retrieval"]
    lines = [
        "# Evaluation report",
        "",
        f"Embedder: `{r['embedder']}`, extractor: `{r['extractor']}`. "
        f"{r['n_products']} datasheets, {ma['rules+semantic']['n']} labelled competitor products.",
        "",
        "## Extraction",
        "",
        f"**{ex['correct']}/{ex['total']} fields correct ({ex['accuracy']:.1%})**",
        "",
        "| Field | Accuracy |",
        "|---|---|",
        *[f"| {k} | {v:.0%} |" for k, v in ex["per_field"].items()],
        "",
        "## Matching",
        "",
        "| Mode | Top-1 | Top-3 | MRR | Hard cases |",
        "|---|---|---|---|---|",
        *[f"| {m} | {v['top1']:.1%} | {v['top3']:.1%} | {v['mrr']:.3f} | {v['hard_cases']} |" for m, v in ma.items()],
        "",
        "## Retrieval (RAG)",
        "",
        "| Mode | Hit@3 |",
        "|---|---|",
        *[f"| {m} | {v['hit@3']:.1%} |" for m, v in re_.items()],
        "",
    ]
    misses = {m: v["misses"] for m, v in ma.items() if v["misses"]}
    if misses:
        lines += ["## Matching misses", ""]
        for m, items in misses.items():
            lines += [f"**{m}**", *[f"- {x}" for x in items], ""]
    if ex["errors"]:
        lines += ["## Extraction errors", "", *[f"- {e}" for e in ex["errors"]], ""]
    return "\n".join(lines)


def main() -> int:
    truth = json.loads((ROOT / "data" / "ground_truth.json").read_text(encoding="utf-8"))
    questions = json.loads((ROOT / "data" / "rag_questions.json").read_text(encoding="utf-8"))
    Session = make_session_factory(make_engine())
    embedder = make_embedder(settings)
    with Session() as s:
        report = {
            "embedder": settings.embedder,
            "extractor": settings.extractor,
            "n_products": len(truth["products"]),
            "extraction": eval_extraction(s, truth),
            "matching": eval_matching(s, truth),
            "retrieval": eval_retrieval(s, embedder, questions),
        }
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "eval.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = to_markdown(report)
    (out / "eval.md").write_text(md, encoding="utf-8")
    print(md)
    return gate(report, json.loads((ROOT / "data" / "thresholds.json").read_text(encoding="utf-8")))


def gate(report: dict, thresholds: dict) -> int:
    """Return 1 (fail CI) if any metric drops below its threshold."""
    checks = {
        "extraction accuracy": (report["extraction"]["accuracy"], thresholds["extraction_accuracy"]),
        "matching top-1": (report["matching"]["rules+semantic"]["top1"], thresholds["matching_top1"]),
        "retrieval hit@3": (report["retrieval"]["hybrid"]["hit@3"], thresholds["retrieval_hit3"]),
    }
    failed = [f"{k}: {v:.3f} < {t}" for k, (v, t) in checks.items() if v < t]
    for f in failed:
        print(f"GATE FAILED  {f}")
    if not failed:
        print("Quality gate passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
