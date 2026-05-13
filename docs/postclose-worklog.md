# Post-Close Worklog

## Current Scope

This worklog is the single rolling record for the post-close mode.

Current confirmed scope:
- Market review generation
- Holdings input and holdings review
- Operations input and operations review
- Next-day observation / execution hints
- Post-close Q&A
- Local demo first

Out of scope for now:
- Broker account connection
- Auto-sync positions or trades
- Intraday real-time replay
- Order placement
- History center as a separate product module

## Current Architecture

The post-close mode now follows a two-layer structure:

1. Fact layer
- Tushare as the main structured market data source
- Supplemental news / topic sources when needed
- Deterministic market facts, flows, limit structure, hotspots, and stock context

2. Explanation layer
- DeepSeek generates readable conclusions on top of the structured facts
- LLM never replaces the fact layer
- All LLM outputs must remain traceable to supplied context

## What Was Finished Before This Round

- Post-close market review route and page flow were already connected
- Holdings review already had fallback + LLM mode
- Operations input UI already supported batch entry
- Post-close Q&A route already existed
- Session split between `postclose` and `midday` already existed
- Context caches already persisted under `result/userdata`

## What Was Finished In This Round

### 1. Operations review is now connected to LLM

File:
- [postclose_operations_service.py](/C:/Users/LENOVO/Documents/Codex/2026-05-02/codex-ai/Ashare/akshare_backend/postclose_operations_service.py)
- [postclose_operations_llm_service.py](/C:/Users/LENOVO/Documents/Codex/2026-05-02/codex-ai/Ashare/akshare_backend/postclose_operations_llm_service.py)

What changed:
- `操作复盘` no longer stops at fallback-only review
- backend now follows the same pattern as holdings review:
  - validate input
  - build market context
  - generate fallback review
  - call DeepSeek when configured
  - merge LLM result with fallback facts
  - save final review into context cache

### 2. Operations review now preserves fact fields

What changed:
- after LLM returns text, the service merges it back with fallback item facts
- this avoids losing fields like `industry` or other deterministic context

### 3. LLM prompt for operations review was rebuilt cleanly

Why:
- the previous file had encoding noise and was harder to maintain
- the new prompt is explicit about:
  - using only supplied facts
  - not inventing market details
  - keeping buy/sell direction consistent
  - returning strict JSON

### 4. Direction consistency was hardened

What changed:
- operations passed to the LLM now include normalized `side_label` values
- prompt explicitly tells the model to obey that label
- this reduces the chance of the model describing a sell as a buy or vice versa

### 5. Runtime garbage was cleaned

What changed:
- removed generated `__pycache__` under `akshare_backend`

## Validation Done

Completed checks:
- `python -m compileall akshare_backend`
- direct local invocation of `build_postclose_operations_review(...)`
- forced refresh run to confirm LLM path is actually used

Observed result:
- `llm_status.used = true`
- model returned structured operations review
- no backend errors in the forced-refresh test

## Current State After This Round

Working now:
- Market review
- Holdings review
- Operations review with LLM
- Post-close Q&A entry
- Cached local demo flow

Still worth improving next:
- tighten operation-review prompt quality further so wording is less noisy
- improve UI readability and spacing for long reports
- strengthen concept / driver evidence for holdings review
- prepare cloud deployment path after local demo stabilizes

## File Hygiene Rule

Continue following these rules:
- remove temporary experiment scripts after use
- keep services flat and single-purpose
- archive things only when they may still matter later
- do not let runtime artifacts accumulate in source directories
