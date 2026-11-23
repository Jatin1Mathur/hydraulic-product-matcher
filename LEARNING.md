# Learning guide: how this project works and how to explain it

Read this top to bottom once, run each command, then do the exercises at the end. After that you can explain every part of the project in an interview.

---

## 1. The problem in one sentence

A customer uses a competitor's pump or valve; we want to find our product that can replace it, and show *why*.

The hard parts are:
- **Messy input**: every manufacturer writes its own units and labels ("p max 31.5 MPa", "Peak pressure 5,000 psi", "Maximum pressure 315 bar" all mean the same kind of thing).
- **Trust**: an engineer will only use a recommendation they can check.

---

## 2. Extraction: from PDF to structured data

**Code:** `src/hpm/pdf.py`, `src/hpm/extract.py`, `src/hpm/schemas.py`

1. `pdfplumber` reads the text and tables of each page.
2. An extractor fills an `ExtractedSpec` (a Pydantic model):
   - **RegexExtractor**: looks for known label synonyms ("Vg max", "Displacement", "Geometric displacement" → displacement). Fast and free, but it only knows labels you taught it.
   - **LLMExtractor**: sends the page text to a local LLM through Ollama, with `format = <JSON schema of ExtractedSpec>`. Ollama then forces the model to return JSON that fits the schema (**structured output**). Pydantic validates it; if it is invalid, the error is sent back once for a retry.

**Three safety ideas to remember:**

| Idea | Where | Why |
|---|---|---|
| The LLM copies values *as written* ("5000", "psi"), it never converts | prompt in `extract.py` | LLMs make arithmetic mistakes; `units.py` is tested code |
| Every number the LLM returns must appear in the PDF text | `_number_in_text` | If it is not there, the model invented it (a **hallucination**), so it is dropped |
| Plausibility limits (e.g. pressure 20–700 bar) | `schemas.PLAUSIBLE` | Catches typos like 35,000 bar |

Try it: `pytest tests/test_extract.py -v`. One test feeds a fake LLM answer with `max_speed: 3000` that is not in the datasheet and checks that it is dropped.

---

## 3. Embeddings: turning text into numbers

**Code:** `src/hpm/embeddings.py`

An **embedding** is a list of numbers (a vector, e.g. 768 numbers) that represents the *meaning* of a text. Texts with similar meaning get vectors that point in a similar direction.

**Cosine similarity** measures that direction: 1.0 = same meaning, about 0 = unrelated.

- `OllamaEmbedder` uses `nomic-embed-text`, a real embedding model. It knows "LS control" ≈ "load sensing regulator".
  Detail worth mentioning: nomic was trained with prefixes, so documents get `search_document: ` and questions get `search_query: `.
- `HashingEmbedder` is an offline stand-in for tests and CI. It hashes words and 3–4 letter pieces into a vector. It catches spelling overlap ("load-sensing" ≈ "load sensing"), but **not meaning**. That is why the semantic-only result in the report is weak in offline mode.

---

## 4. pgvector: storing and searching vectors in PostgreSQL

**Code:** `src/hpm/db.py`, `src/hpm/search.py`

- `pgvector` adds a `vector(768)` column type to PostgreSQL.
- `embedding <=> query_vector` is the cosine *distance* (0 = identical). `ORDER BY ... LIMIT 20` gives the 20 closest chunks.
- An **HNSW index** (`chunks_embedding_hnsw`) makes this fast: it is a graph that finds *approximately* nearest neighbours without comparing against every row.

**Why PostgreSQL instead of a separate vector database?** Specs, provenance, full-text search and vectors live in one place, so one query can filter by SQL (manufacturer, type) *and* search by vector. Fewer moving parts.

---

## 5. Hybrid search and RRF

**Code:** `src/hpm/search.py`

| Retriever | Good at | Bad at |
|---|---|---|
| Vector (pgvector) | synonyms, meaning | exact codes ("VT-D6"), standards ("ISO 4406 19/17/14") |
| Keyword (PostgreSQL full-text: `tsvector`, `ts_rank_cd`, GIN index) | exact terms | synonyms |
| Model code lookup | a product code typed in the question | everything else |

**Reciprocal Rank Fusion (RRF)** merges the ranked lists: each result gets `1 / (60 + rank)` from every list it appears in, and the scores are added. It only uses *ranks*, so you never have to compare a cosine distance with a text-rank score.

Measured on 16 labelled questions: vector 93.8 %, keyword 100 %, hybrid 100 % (hit@3).

Also notice **contextual chunk headers** in `pdf.py`: every chunk starts with the datasheet title, so a chunk that only says "Q max 100 l/min" still tells the search which product it belongs to.

---

## 6. RAG: answering questions from the documents

**Code:** `src/hpm/rag.py`

**RAG = Retrieval-Augmented Generation:**
1. **Retrieve** the most relevant chunks (hybrid search).
2. **Augment** the prompt: put them in as numbered context `[1] [2] [3]`.
3. **Generate**: the LLM answers *only* from that context and cites `[n]`; if the answer is not there it must say "Not found in the datasheets".

Why: the model answers from *our* documents, not from its memory, and every answer points to a page the user can open.

---

## 7. Matching: rules first, AI second

**Code:** `src/hpm/matching.py`

1. **Hard rules** (engineering knowledge, readable by anyone):
   - same component type and circuit (open ≠ closed)
   - displacement within ±20 %
   - pressure, speed and flow ratings at most 5 % below the competitor's
   - valve interface must match (NG6 = D03 = CETOP 3)
2. **Spec score**: weighted closeness per attribute, e.g. displacement 45 %.
3. **Semantic score**: cosine similarity of the feature/control descriptions.
4. `total = 0.8 × spec + 0.2 × semantic`, compatible candidates first.

Two details that show engineering thinking:
- **Right-sizing**: a much bigger valve also "works" but costs more, so oversizing gets a mild penalty (`_rating`).
- **Missing data is not a failure**: it is shown as "check manually".

**The evidence (hard cases):** for `VT-G19` (19.5 cm³, 275 bar) the closest size is OW-G22, but it is only rated 250 bar. The rules pick OW-G16 instead. The naive baseline gets 1 of 4 hard cases right; rules get 4 of 4.

---

## 8. Evaluation: how you know it works

**Code:** `src/hpm/evaluate.py`, report in `reports/eval.md`

| Metric | Meaning |
|---|---|
| Extraction accuracy | share of fields equal to the true value (numbers within 2 %, because catalogues round) |
| Top-1 / Top-3 | the correct product is first / in the first three |
| MRR (mean reciprocal rank) | average of 1/rank of the correct answer: 1.0 = always first, 0.5 = usually second |
| Hit@3 | for search: the right document is in the top 3 results |

**Ablation** = turning parts off to see what each one contributes (naive → semantic → rules → rules+semantic). That is how you *prove* that the rules matter.

**Quality gate**: `data/thresholds.json`. If a code change makes a metric drop below the threshold, CI fails.

---

## 9. Interview questions and good answers

**"Why not just ask an LLM which product matches?"**
It can't be checked, it may invent specs, and it is weak at numeric comparisons. I use the LLM where it is strong (reading messy text) and deterministic rules where correctness matters, and every recommendation lists the criterion behind it.

**"How do you stop hallucinations?"**
Three layers: JSON-schema structured output plus Pydantic validation; every extracted number must appear verbatim in the source PDF; plausibility ranges. In RAG, the model must answer only from cited passages or say "not found".

**"Why hybrid search?"**
Embeddings miss exact identifiers and standards; keyword search misses synonyms. I measured both: vector alone 93.8 % hit@3, hybrid 100 %. RRF merges them without calibrating scores.

**"Why pgvector and not Pinecone/Chroma?"**
The product data is relational and needs SQL filters anyway. One PostgreSQL with pgvector handles specs, provenance, full-text and vectors, with an HNSW index. A separate vector DB would only be worth it at much larger scale.

**"What does your accuracy really mean?"**
The demo data is synthetic, so 100 % shows the pipeline and rules work, not real-world accuracy. The next step is real catalogues and a labelled set built with product experts. The evaluation and the feedback loop are built for exactly that.

**"How would you take this to production?"**
Real labelled data with experts; a feedback button in the UI to accept or reject matches, stored as new test cases; Alembic migrations; background ingestion; authentication; monitoring of extraction warnings.

**"What would you change in the weights?"**
They are a starting point in one config place. With expert feedback, I would tune them on the labelled set and check with the ablation that each change helps.

---

## 10. Exercises (do these yourself before the interview)

1. **Run it with a real LLM.** Install Ollama, `ollama pull qwen2.5:7b nomic-embed-text`, set `EMBEDDER=ollama EXTRACTOR=llm RAG_LLM=true`, then `hpm init-db --reset && hpm ingest data/datasheets && hpm eval`. Compare the report with the offline one. Write the real numbers into your CV.
2. **Break it on purpose.** In `scripts/catalog.py`, change OW-G16's max pressure to 260 bar, regenerate, re-ingest and run `hpm match VT-G19`. Explain what happens and why.
3. **Add a label synonym.** Make one brand call displacement "Swept volume". Watch the regex extractor fail and the LLM extractor still work. This is the argument for the LLM.
4. **Add a component type**, e.g. hydraulic motors, with their own rules.
5. **Add one real datasheet** (a public PDF) into `data/datasheets/competitors/` and see what extraction finds. Note what breaks; that is your "lessons learned" story.
