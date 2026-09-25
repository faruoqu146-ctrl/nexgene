# NexGene v1.3.0

## Phase 6: Personal Health Intelligence

NexGene v1.3.0 extends the tested v1.1.x foundation with a new molecular / biomarker signal layer and an evidence-aware intelligence foundation.


### Phase 6 additions

- **Personal baseline engine**: compares recent 7-day windows with a preceding 21-day personal baseline.
- **Multi-factor longitudinal analysis**: exploratory daily associations across sleep, focus, energy, stress, activity, caffeine and related signals. Associations are explicitly non-causal.
- **Data-quality surface**: reports coverage, observed days, signal counts and biomarker quality so sparse data is not presented as certainty.
- **Evidence-linked inference**: detected patterns generate topic signals for the local evidence registry.
- **Structured intelligence insights**: `/api/v1/intelligence/insights` separates observed findings from inferred findings, evidence, uncertainty and next steps.
- **Clinical escalation remains bounded**: v1.3 can recommend discussing persistent molecular deviations with a qualified professional, but it does not perform clinical triage or diagnosis.

### New architectural layers

- **Molecular / Biomarker signals**: supports sensor-style deviation signals as well as quantitative laboratory values. A deviation signal records direction/significance/confidence without pretending to be a concentration.
- **Evidence registry**: structured records for guidelines, research, medical reports, clinical references, and reviews, with provenance fields and topic tags.
- **Evidence retrieval**: authenticated search over the local evidence registry. Development-only batch import is available for loading a curated knowledge pool.
- **Intelligence brief**: combines longitudinal lifestyle/physiological observations with molecular signals and retrieves relevant evidence. It explicitly separates observations from inferences and keeps clinical escalation as a distinct, currently unassessed layer.
- **AI handoff**: the optional AI weekly read now receives the bounded weekly report plus the structured intelligence brief, rather than raw unrestricted health history.

### Four-pillar direction remains intact

Lifestyle, physiological, clinical, and genetic data remain peer scientific pillars. The molecular / biomarker layer adds another evidence stream without replacing those pillars. Clinical and genetic ingestion remain out of scope for this release.

### Security boundaries

- Biomarker writes are authenticated and CSRF protected.
- Biomarker data is scoped to the authenticated user.
- Deviation-mode signals cannot carry a fake quantitative concentration.
- Evidence import is development-only in v1.2.0.
- AI remains opt-in and server-side.
- The AI layer is instructed to use only structured evidence, avoid diagnosis/treatment claims, and preserve uncertainty.

### Important limitation

The evidence registry is an architectural foundation, not a populated medical knowledge base. It does not claim that a large medical literature corpus is present in this development build. Production knowledge retrieval will require a curated, provenance-preserving corpus, ingestion/update pipeline, source validation, retrieval/ranking, and a separate clinical-safety review.

### Development

```bash
docker compose up --build
```

API: `http://localhost:8000`

Docs are available only while `DEV_MODE=true`.

### Version

`APP_VERSION = 1.3.0`

### Retained product layers

- NexGene Signals
- Weekly NexGene Report
- Molecular / Biomarker signal layer
- Evidence registry and evidence-aware intelligence
