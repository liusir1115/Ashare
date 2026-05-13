# Public Deployment Plan

## Goal

Deploy the current local demo as a small shared web service for roughly 10 to 20 users.

The target shape is:
- one shared backend service
- one shared web page
- all market data and LLM calls happen on the server
- users only open the website and submit forms

## Why This Is Feasible

This project is already close to a deployable single-service app:
- frontend is static files
- backend is a Flask app
- Tushare and DeepSeek are already server-side calls
- user drafts and review caches already persist under `result/userdata`

For a small friend-group scale, one lightweight server is enough.

## Recommended First Deployment Shape

### Version 1

- 1 cloud server
- Ubuntu 22.04
- Python virtual environment
- Flask app running behind a process manager
- Nginx reverse proxy
- one domain or raw IP access

### Suggested server size

- 2 vCPU
- 4 GB RAM
- 40 GB disk

This is enough for low-concurrency shared use.

## Required Configuration Changes

Before public deployment, the app should run from environment variables instead of local private runtime files.

Already prepared:
- `.env.example`
- `ASHARE_HOST`
- `ASHARE_PORT`
- `TUSHARE_TOKEN`
- `TUSHARE_HTTP_URL`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`

## Deployment Boundary

Current first public version should include:
- premarket screening
- post-close market review
- holdings review
- operations review
- post-close Q&A

Current first public version should not include:
- broker connection
- auto position sync
- auto trade sync
- order placement
- public registration system

## Data and Secret Ownership

In public deployment mode:
- only the server stores tokens
- users do not need local Python
- users do not touch Tushare keys
- users do not touch DeepSeek keys

## Persistence Plan

For the first public version, keep persistence simple:
- retain `result/`
- retain `result/userdata/`
- optionally add SQLite later if we need user isolation or multi-user history

## Risks To Watch

### 1. Secret exposure

The current repo must never commit real keys.

### 2. Shared drafts

Right now draft files are global, not per-user.

That is acceptable for local demo work, but before wider public sharing we should add either:
- a simple login/password gate, or
- a lightweight user id/session isolation layer

### 3. Data refresh latency

For a small user group, current on-demand pull is acceptable, but later we may want:
- timed cache refresh
- background update jobs

## Recommended Next Step

1. Finish environment-variable deployment shape
2. Add a minimal production startup command
3. Deploy to one server for internal use
4. Test with 2 to 3 friends first
5. Then widen to the full small group
