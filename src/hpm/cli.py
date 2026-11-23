"""Command line interface.

hpm init-db [--reset]
hpm ingest data/datasheets
hpm products [--reference | --competitors]
hpm match NH-P30 [--mode rules+semantic] [--top-k 3]
hpm ask "Which cleanliness level does Vantek require?"
hpm eval
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hpm import service
from hpm.config import settings
from hpm.db import init_db, make_engine, make_session_factory
from hpm.embeddings import make_embedder


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hpm", description="Hydraulic product matcher")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init-db")
    p.add_argument("--reset", action="store_true", help="drop and recreate all tables")
    p = sub.add_parser("ingest")
    p.add_argument("folder", type=Path)
    p = sub.add_parser("products")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--reference", action="store_true")
    g.add_argument("--competitors", action="store_true")
    p = sub.add_parser("match")
    p.add_argument("model")
    p.add_argument("--mode", default="rules+semantic", choices=["naive", "rules", "rules+semantic", "semantic"])
    p.add_argument("--top-k", type=int, default=3)
    p = sub.add_parser("ask")
    p.add_argument("question")
    p.add_argument("--manufacturer")
    sub.add_parser("eval")
    args = ap.parse_args(argv)

    engine = make_engine()
    Session = make_session_factory(engine)
    embedder = make_embedder(settings)

    if args.cmd == "init-db":
        init_db(engine, reset=args.reset)
        print(f"Database ready (embedder={settings.embedder}, dim={settings.embed_dim})")
    elif args.cmd == "ingest":
        extractor = service.make_extractor(settings)
        with Session.begin() as s:
            results = service.ingest_folder(s, args.folder, embedder, extractor)
        for r in results:
            print(f"{r.status:10} {r.filename:20} {r.model or ''}")
            for w in r.warnings:
                print(f"           ! {w}")
        print(
            f"{sum(r.status == 'ingested' for r in results)} ingested, "
            f"{sum(r.status == 'unchanged' for r in results)} unchanged, "
            f"{sum(r.status == 'failed' for r in results)} failed"
        )
    elif args.cmd == "products":
        ref = True if args.reference else False if args.competitors else None
        with Session() as s:
            for p in service.list_products(s, reference=ref):
                size = p.nominal_size or (f"{p.displacement:g} cm3/rev" if p.displacement else "")
                print(
                    f"{p.manufacturer.name:10} {p.model:10} {p.component_type:20} {size:14} "
                    f"{p.max_pressure or 0:6.0f} bar"
                )
    elif args.cmd == "match":
        with Session() as s:
            try:
                results = service.match(s, args.model, mode=args.mode, top_k=args.top_k)
            except KeyError:
                print(f"Unknown product {args.model}", file=sys.stderr)
                return 1
        for i, m in enumerate(results, start=1):
            flag = "OK " if m.compatible else "NO "
            print(
                f"{i}. [{flag}] {m.reference.model:8} total {m.total:.2f}  "
                f"(spec {m.spec_score:.2f}, semantic {m.semantic_score:.2f})"
            )
            for c in m.criteria:
                mark = {True: "+", False: "x", None: "?"}[c.passed]
                print(f"      {mark} {c.detail}")
    elif args.cmd == "ask":
        from hpm.llm import OllamaClient
        from hpm.rag import answer

        llm = OllamaClient(settings.ollama_url, settings.llm_model) if settings.rag_llm else None
        with Session() as s:
            a = answer(s, embedder, args.question, llm=llm, manufacturer=args.manufacturer)
        print(a.text)
        if a.generated:
            print("\nSources:")
            for h in a.citations:
                print(f"  {h.filename}, page {h.page}")
    elif args.cmd == "eval":
        from hpm.evaluate import main as eval_main

        return eval_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
