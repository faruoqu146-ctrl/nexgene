# NexGene Evidence Pool

This directory defines the shape of the future evidence corpus. It is intentionally not populated with medical claims in v1.2.0.

Evidence records should preserve provenance and distinguish source classes such as:

- clinical guidelines
- peer-reviewed research
- systematic reviews
- medical reports
- clinical reference material

Each record should retain title, publisher, citation, publication year, URL where available, evidence grade, topic tags, and a concise source summary.

The development API can import curated batches while `DEV_MODE=true`. Production ingestion must use a reviewed pipeline with source validation, deduplication, update/version tracking, and auditability.
