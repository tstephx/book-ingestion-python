# Triage

| Symptom | Check |
|---------|-------|
| Chapter boundaries wrong | `python -m book_ingestion.cli analyze <book-id>` — inspect detected TOC/anchors |
| Long chapters (>15K tokens) | Confirm section_splitter behavior; check if semantic boundaries exist |
| Embeddings fail | Verify Python 3.12 (not 3.13), torch installed, rerun `generate_embeddings.py` |
| MCP server doesn't see new books | Confirm embeddings generated, then restart/reload MCP host |
| DB mismatch | See `.claude/skills/db-schema/SKILL.md` — canonical vs. dev-copy path resolution and current known gaps |
