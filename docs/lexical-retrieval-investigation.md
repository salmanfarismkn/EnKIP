# Lexical Retrieval Investigation

## Finding

The held-out lexical score of 0.000 Recall@5 and 0.000 MRR@5 is explained by
query-to-lexeme mismatch, not by missing vectors, tenant/user filtering, joins,
or evaluation wiring. The existing baseline uses compact queries whose terms
match a single indexed chunk. The held-out cases use natural-language
paraphrases; PostgreSQL's `websearch_to_tsquery('english', ...)` requires the
non-stopword terms in the query to match one chunk's `search_vector`. Stemming
helps inflections, but it does not map synonyms such as “examine” to “inspect”.

No production retrieval algorithm or held-out label was changed. A separate
development dataset and report record the reproductions. The held-out evaluator
and report were not rerun or rewritten during this investigation.

## Evidence

The read-only baseline probe used `banking-001`, query `consortium banks data
warehouse loan schemes`, and its expected document from the existing baseline.
The document existed in the requested tenant, its data source was accessible
to the evaluation user, its one chunk had a non-null, non-empty vector, direct
`@@` matching found that chunk, and `LexicalSearchService.search` returned the
expected document. PostgreSQL produced:

```text
'consortium' & 'bank' & 'data' & 'warehous' & 'loan' & 'scheme'
```

For held-out case `heldout-001`, the unchanged query is `When should engineers
examine the tidal rotor blades at the Aurelia array?`. A read-only PostgreSQL
probe against the held-out seeder's static synthetic text produced:

```text
'engin' & 'examin' & 'tidal' & 'rotor' & 'blade' & 'aurelia' & 'array'
```

No individual chunk matched; concatenating the document's chunks did not match
either. In the synthetic source, the topic terms are present, but the query's
`engineer` and `examine` lexemes are not. This is sufficient to explain that
representative miss without rerunning the held-out benchmark. The held-out
report also shows vector and hybrid retrieval returning the expected IDs, and
the original evaluator wires the same query, tenant, and user to each method.

The separate development run reproduced these behaviors:

| Development case | Expected document | Direct chunk matches | Service outcome |
|---|---|---:|---|
| `lexdev-exact-001`, `helium lattice annealing` | `f4000000-0000-4000-8000-000000000001` | 1 | Returned |
| `lexdev-paraphrase-001`, `heat treatment stabilizes crystalline grain boundaries` | `f4000000-0000-4000-8000-000000000001` | 0 | Authorized lexical miss |
| `lexdev-identifier-001`, `PX-410B` | `f4000000-0000-4000-8000-000000000002` | 1 | Returned |
| `lexdev-identifier-002`, `7A-2` | `f4000000-0000-4000-8000-000000000002` | 1 | Returned |
| `lexdev-multichunk-same-001`, `quartz feldspar assay boron` | `f4000000-0000-4000-8000-000000000003` | 1 | Returned |
| `lexdev-multichunk-split-001`, `luminous quartz assay` | `f4000000-0000-4000-8000-000000000003` | 0 | Authorized lexical miss |
| `lexdev-unauthorized-001`, Alice querying the restricted record | `f4000000-0000-4000-8000-000000000004` | 1 | Withheld |
| `lexdev-authorized-restricted-001`, Bob querying the same record | `f4000000-0000-4000-8000-000000000004` | 1 | Returned |

All expected development documents existed and had non-null, non-empty vectors.
The unauthorized case directly matched its restricted chunk, was withheld from
Alice, and was returned to Bob. The multi-chunk control shows that retrieval
matches within each chunk vector; terms distributed across different chunks do
not form a document-wide match. The identifier queries demonstrate PostgreSQL's
punctuation-sensitive tokenization (`PX-410B` becomes a phrase-like tsquery),
but the exact stored forms match. Identifiers are not the cause of the held-out
failures.

## Pipeline And Index

- `ChunkService.replace_chunks` inserts chunks and flushes them. The lexical
  migration's enabled `BEFORE INSERT OR UPDATE OF text` trigger populates
  `search_vector` with `to_tsvector('english', coalesce(text, ''))`; the
  development seeder relied on this trigger and verified every vector.
- The active PostgreSQL default is `pg_catalog.english`. Both vector population
  and query parsing explicitly use `english`.
- `LexicalSearchService` builds `websearch_to_tsquery`, computes
  `ts_rank_cd`, filters with `search_vector @@ ts_query`, and orders by rank.
  The match occurs before ranking; a query with a missing required lexeme
  produces no candidate to rank.
- The service joins chunks to versions, documents, and data sources. It filters
  by chunk tenant and the user's accessible data-source IDs. Development
  probes confirmed the same matching restricted document was inaccessible to
  Alice but accessible to Bob; no permission defect was found.
- The evaluator loads each case's query, tenant, user, and expected IDs and
  passes the same query and access context to all retrieval strategies. The
  expected baseline document was verified against the database and production
  lexical service.

The investigation also found an independent performance regression. The
lexical migration creates `ix_document_chunks_search_vector` as a GIN index,
but migration `88e38008b930_add_knowledge_graph_tables` drops it in `upgrade()`.
The active database at revision `9fdbadce35c6` had the trigger and populated
vectors but no GIN index. Migration `a8fd8271c5d9` restores the index
idempotently. This index affects search performance, not `@@` truth or the
Recall/MRR discrepancy.

## Artifacts And Limits

- Development labels: `tests/evaluation/lexical_development_cases.json`.
- Synthetic corpus: `scripts/lexical_dev_corpus.py`.
- Reproducible runner: `scripts/run_lexical_dev_experiment.py`.
- Development report: `reports/lexical_development_experiment_report.json`.
- Regression for the GIN index: `tests/integration/test_permission_aware_retrieval.py`.

The experiment uses four synthetic documents and eight cases. It is diagnostic,
not a quality estimate. Its database rows are rolled back and cleanup is
verified. The held-out report and baseline report were left untouched by the
diagnostic run. No query expansion or retrieval tuning was performed.