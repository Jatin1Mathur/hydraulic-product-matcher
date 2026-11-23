"""Streamlit prototype UI.   Run:  streamlit run ui/app.py

Pick a competitor product -> ranked replacement candidates with the reason for every
score -> side-by-side spec comparison -> ask questions about the datasheets (RAG).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from hpm import service
from hpm.config import settings
from hpm.db import make_engine, make_session_factory
from hpm.embeddings import make_embedder
from hpm.llm import OllamaClient
from hpm.rag import answer

st.set_page_config(page_title="Hydraulic Product Matcher", layout="wide")

ROWS = [  # (label, attribute, unit)
    ("Manufacturer", None, ""),
    ("Component type", "component_type", ""),
    ("Circuit", "circuit", ""),
    ("Mounting", "mounting", ""),
    ("Nominal size", "nominal_size", ""),
    ("Displacement", "displacement", "cm³/rev"),
    ("Max. pressure", "max_pressure", "bar"),
    ("Continuous pressure", "cont_pressure", "bar"),
    ("Max. speed", "max_speed", "rpm"),
    ("Max. flow", "max_flow", "L/min"),
    ("Weight", "weight", "kg"),
    ("Control / features", "control_text", ""),
]


@st.cache_resource
def resources():
    return make_session_factory(make_engine()), make_embedder(settings)


Session, embedder = resources()


def fmt(v, unit):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:g} {unit}".strip()
    return str(v)


def comparison_table(comp, ref) -> pd.DataFrame:
    data = []
    for label, attr, unit in ROWS:
        a = comp.manufacturer.name if attr is None else getattr(comp, attr)
        b = ref.manufacturer.name if attr is None else getattr(ref, attr)
        delta = f"{(b - a) / a * 100:+.1f} %" if isinstance(a, float) and isinstance(b, float) and a else ""
        data.append({"Attribute": label, comp.model: fmt(a, unit), ref.model: fmt(b, unit), "Δ": delta})
    return pd.DataFrame(data).set_index("Attribute")


st.title("Hydraulic Product Matcher")
st.caption(f"Embedder: {settings.embedder} · Extractor: {settings.extractor} · demo data is fictional")

tab_match, tab_ask, tab_db = st.tabs(["Find replacement", "Ask the datasheets", "Database"])

with Session() as s:
    competitors = service.list_products(s, reference=False)

with tab_match:
    if not competitors:
        st.warning("No products yet. Run `hpm init-db` and `hpm ingest data/datasheets` first.")
        st.stop()
    labels = {f"{p.manufacturer.name} {p.model} ({p.component_type.replace('_', ' ')})": p.model for p in competitors}
    col1, col2, col3 = st.columns([3, 2, 1])
    choice = col1.selectbox("Competitor product", list(labels))
    mode = col2.selectbox("Matching mode", ["rules+semantic", "rules", "semantic", "naive"])
    top_k = col3.number_input("Top-k", 1, 10, 3)

    with Session() as s:
        comp = service.get_product(s, labels[choice])
        results = service.match(s, comp.model, mode=mode, top_k=int(top_k))
        refs = {m.reference.model: service.get_product(s, m.reference.model) for m in results}

    for i, m in enumerate(results, start=1):
        badge = "✅ compatible" if m.compatible else "❌ not compatible"
        with st.expander(f"{i}. {m.reference.model} · score {m.total:.2f} · {badge}", expanded=i == 1):
            c1, c2, c3 = st.columns(3)
            c1.metric("Total", f"{m.total:.2f}")
            c2.metric("Spec score", f"{m.spec_score:.2f}")
            c3.metric("Semantic score", f"{m.semantic_score:.2f}")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Check": c.name,
                            "Rule": "hard" if c.hard else "soft",
                            "Result": {True: "pass", False: "FAIL", None: "missing"}[c.passed],
                            "Score": round(c.score, 2),
                            "Detail": c.detail,
                        }
                        for c in m.criteria
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
            st.markdown("**Side-by-side**")
            st.dataframe(comparison_table(comp, refs[m.reference.model]), width="stretch")

    with Session() as s:
        sources = service.get_product(s, comp.model).sources
    with st.expander("Where did the competitor values come from?"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Attribute": x.attribute,
                        "As printed": x.raw,
                        "Page": x.page,
                        "Method": x.method,
                        "Verified in source": x.verified,
                    }
                    for x in sources
                ]
            ),
            hide_index=True,
            width="stretch",
        )

with tab_ask:
    q = st.text_input("Question", "Which cleanliness level does the VT-AX45 require?")
    if st.button("Ask") and q:
        llm = OllamaClient(settings.ollama_url, settings.llm_model) if settings.rag_llm else None
        with Session() as s:
            a = answer(s, embedder, q, llm=llm)
        st.write(a.text)
        for h in a.citations:
            st.caption(f"Source: {h.filename}, page {h.page}")

with tab_db:
    with Session() as s:
        rows = service.list_products(s)
        df = pd.DataFrame(
            [
                {
                    "Manufacturer": p.manufacturer.name,
                    "Own portfolio": p.manufacturer.is_reference,
                    "Model": p.model,
                    "Type": p.component_type,
                    "Circuit": p.circuit,
                    "Size": p.nominal_size,
                    "Displacement cm³": p.displacement,
                    "p max bar": p.max_pressure,
                    "n max rpm": p.max_speed,
                    "Q max L/min": p.max_flow,
                    "kg": p.weight,
                }
                for p in rows
            ]
        )
    st.dataframe(df, hide_index=True, width="stretch")
