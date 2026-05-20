# Copilot Instructions for ml-server

## Purpose
This file defines generic agent behavior for this repository.
Use a document-first workflow and keep architecture decisions anchored in core docs.

## Priority Order
Read and follow these documents in order before non-trivial changes:
1. ml-server/docs/Main.md
2. ml-server/docs/UNIFIED.md
3. ml-server/docs/API/MAIN.md
4. ml-server/docs/COMMON_MODEL_INTERFACE.md
5. ml-server/docs/MODEL_STORAGE_STRUCTURE.md
6. ml-server/docs/MLFLOW_CACHE_CONTEXT.md
7. ml-server/procedures/REQUEST-RESPONSE SEQUENCES.md

## Required Document Checklist
- Review applicable docs before editing behavior, API contracts, model loading, or runtime workflows.
- If code changes alter documented behavior, update the relevant docs in the same change.
- If docs and code diverge, align code with approved behavior and then reconcile documentation.
- If a required doc is missing, state this explicitly and proceed with available sources.

## Working Rules
- Prefer minimal, safe, additive changes over broad refactors.
- Reuse existing helpers and conventions instead of introducing ad-hoc patterns.
- Preserve backward compatibility unless the task explicitly requires a breaking change.
- Keep request/response contracts stable unless a contract update is part of the task.
- Keep diffs focused; avoid unrelated formatting churn.

## Change Management
- For architecture-impacting changes, verify consistency with ml-server/docs/Main.md.
- For API-impacting changes, verify consistency with contract documents before implementation.
- Record assumptions and residual risks when requirements are ambiguous.

## Validation & Delivery
- Validate with targeted tests first, then broader tests as needed.
- Include negative-path checks when touching validation or error handling.
- Summarize what changed, why it changed, and how it was validated.
- Include follow-up tasks when scope was intentionally limited.
