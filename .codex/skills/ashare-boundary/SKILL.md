---
name: ashare-boundary
description: Guardrails for planning, implementing, reviewing, or restructuring work inside the Ashare repository. Use when changing product scope, editing architecture, adding postclose features, integrating LLM or APIs, coordinating with collaborators, or deciding which files may be changed.
---

# Ashare Boundary

Use this skill before making meaningful changes in the `Ashare` repository.

## Core Goal

Keep all work inside the agreed project boundary:

- Treat `Ashare` as one product with `盘前` and `盘后` modes
- Focus the current development cycle on `盘后 local demo`
- Extend the existing project instead of rebuilding it from scratch
- Prefer small entry-point edits plus new modules
- Keep collaboration safe, reversible, and branch-friendly

## Current Scope

For the current cycle, implement only:

- 市场总复盘
- 持仓录入与持仓复盘
- 操作录入与操作复盘
- 盘后问答
- Markdown 导出
- 本地结果保存

Do not expand scope to:

- 历史复盘中心
- 券商接入
- 自动同步持仓或成交
- 盘中实时复盘
- 小程序形态
- 公网部署 implementation work

Read `references/boundary-rules.md` when scope or feature ownership is unclear.

## Architecture Rules

- Reuse the existing Flask backend and frontend shell
- Add new postclose modules instead of rewriting premaket logic
- Keep LLM calls in the backend, never in the frontend
- Use structured JSON as the boundary between data prep, LLM generation, and UI rendering
- Keep generated result files, caches, logs, and secrets out of git

Prefer this shape:

- `akshare_backend/app.py`: route registration only
- `akshare_backend/service.py`: existing premarket services
- `akshare_backend/postclose_service.py`: postclose orchestration
- `akshare_backend/llm_client.py`: model adapter
- `frontend/`: shared UI shell plus postclose views
- `docs/`: product and implementation docs

## File Change Policy

- Allow small edits to shared entry files when required to connect new features
- Prefer new files for postclose business logic
- Do not refactor unrelated premarket code unless the task explicitly requires it
- Do not delete or rewrite coworker work without approval
- Preserve the visual language of the existing product

## Collaboration Rules

- Treat `main` as the stable baseline
- Make changes on feature branches when collaborating
- Keep commits focused and reversible
- Do not commit local environment noise, proxy settings, logs, or generated spreadsheets
- Surface conflicts early instead of silently working around them

## Execution Workflow

1. Read the relevant docs in `docs/`
2. Inspect the existing entry points before editing
3. Confirm the change belongs to the current scope
4. Prefer additive implementation with minimal shared-file edits
5. Validate behavior locally
6. Summarize what changed, why it belongs in scope, and any remaining risks

## References

- Read `references/boundary-rules.md` for the detailed project boundary
