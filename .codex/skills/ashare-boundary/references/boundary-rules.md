# Ashare Boundary Rules

## 1. Product Boundary

The repository represents one A-share product with two modes:

- `盘前模式`: existing stock screening workflow
- `盘后模式`: current focus for the new local demo

Current active delivery target:

- `盘后模式 local demo`

## 2. In-Scope Work

The current implementation phase may include:

- Market review generation
- Holdings input and holdings review
- Operation input and operation review
- Postclose Q&A
- Markdown export
- Local result persistence
- LLM backend integration
- API design needed for the postclose workflow
- UI updates needed to expose postclose pages inside the existing product shell

## 3. Out-of-Scope Work

Do not proactively add these:

- Broker connectivity
- Auto-sync positions
- Auto-sync orders or fills
- Historical review center
- Intraday monitoring
- Public deployment implementation
- Multi-user system
- Mobile mini-program adaptation
- Strategy marketplace or commercial subscription logic

## 4. Code Structure Boundary

Prefer additive changes over rewrites.

Expected implementation pattern:

- Keep the existing project root
- Reuse `frontend/` and `akshare_backend/`
- Add postclose-specific modules rather than overloading premarket files
- Keep model adapters behind a backend interface
- Keep UI rendering separate from LLM output generation

## 5. Shared-File Rule

Shared files may be edited only when needed to wire in new capability, for example:

- route registration
- navigation entry
- shared style tokens
- shared export hooks

Avoid broad rewrites in shared files.

## 6. Git and Collaboration Boundary

- `main` is the rollback-safe baseline
- Prefer feature branches for ongoing work
- Never overwrite unknown coworker changes
- Review git status before committing
- Keep commits narrow and message them clearly

## 7. Data and Security Boundary

- Do not commit API keys
- Do not commit proxy credentials
- Do not commit local logs
- Do not commit generated Excel results unless explicitly requested
- Mark external-data failures clearly instead of fabricating fallback facts
- Do not leave runtime caches, temporary validation scripts, or one-off diagnostics mixed into the main product paths after their purpose is complete
- Archive dormant-but-possibly-useful helper files into an explicit archive area instead of keeping them beside active production files

## 8. LLM Boundary

- LLM calls belong in backend service modules
- Frontend should call backend APIs, not model providers
- Facts must come from structured upstream data
- Missing data must be labeled as limited or degraded, not invented

## 9. UX Boundary

- Keep the postclose experience visually aligned with the existing premarket product
- Do not introduce a separate design language
- Prefer concise report output over long essay-style output

## 10. Decision Rule

If a proposed change is outside the current scope, do one of these:

1. reject it for the current cycle
2. move it to a later-phase note in `docs/`
3. ask for an explicit scope expansion before implementing

## 11. Reporting Rule

After each completed development step, provide a structured update that helps the user audit progress.

The update should cover:

- changed files
- new files
- untouched critical files
- structural effect on the repository
- actual functional changes versus placeholder scaffolding
- next step recommendation

The goal is to make every iteration easy to review even for a non-expert collaborator.

## 12. Cleanup Rule

Repository cleanliness is part of the delivery contract.

- Prefer deleting runtime garbage over preserving it
- Prefer archiving dormant helpers over leaving them in active directories
- Keep active directories focused on current product logic
- When cleanup is performed, distinguish:
  - deleted runtime garbage
  - archived helper material
  - untouched core product files
