# ADR 0007: Deterministic, explainable intelligence before machine learning

**Status:** Accepted (Phase 5)

**Decision.** Classification, location extraction, summarisation, duplicate detection,
clustering and risk scoring are deterministic: administrator-maintained keyword rules,
matching of official unit names, extractive summaries, PostgreSQL trigram similarity
and configurable weighted factors. Every output stores model id, version, confidence,
evidence, input hash and review status. Suggestions change a grievance only when an
officer accepts or edits them.

**Why.** No representative, lawfully processed training data or validation method exists
yet. A trained model without them could not be evaluated, so no accuracy is claimed.
The pipeline and data model are ready for a validated model later: it would plug in as
another `model_id`/`model_version` with the same review workflow.
