# 0003. Auth fails closed; demo mode still requires a token

* Status: accepted
* Date: 2026-06-05
* Ported from: `docs/ROADMAP.md` §6 (2026-07-05, form only — content unchanged)

## Context and Problem Statement

A reading history is sensitive — it can out someone — so the dashboard must never be reachable
without authentication, in any mode, including local demo/dev use.

## Decision Outcome

Non-demo startup raises if `STACKS_AUTH_TOKEN` is unset (no accidental open instance); demo mode
uses a fixed token so there is never an unauthenticated path. Enforced by `tests/test_auth.py`
(merge-blocking).

## Rejected Options

* An "open in demo" bypass — rejected because a reading history is sensitive even in demo mode, and
  an exception here would be an easy-to-miss regression vector later.
