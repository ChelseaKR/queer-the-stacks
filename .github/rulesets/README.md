# Branch-protection ruleset — committed artifact (CICD-12)

`main.proposed.json` is the ruleset this repository proposes for the `main` branch, committed as
the artifact `STANDARDS/CI-CD-STANDARD.md` (CICD-12) asks for.

## Correction, 2026-08-29 — two things this file said were wrong

Both of the following were load-bearing, and both are reversed below rather than quietly deleted,
because the reasoning that produced them is the part worth not repeating.

**1. This file used to carry `"bypass_actors": []`, and this README used to walk a reader through
posting it.** Following these instructions was enough to lock the owner out of her own repository.
That is not hypothetical: applying a no-bypass ruleset elsewhere in this portfolio took a manual
recovery sweep across eighteen repositories. GitHub answers such a POST with `201 Created` like any
other, so nothing warns you at the moment you do it.

**2. This README used to state that "as of 2026-07-05, no branch protection or ruleset is actually
active on this repo", and justified the `.proposed` suffix on that basis.** That claim was true
when it was written and is false now. A ruleset **is** applied and has been since 2026-07-09; it
was last updated 2026-08-26. It is enumerated below. The `.proposed` suffix is kept, but its
meaning has changed: it no longer means "nothing is applied", it means "this file is not what is
applied", which is a different and more dangerous condition, because the two disagree.

## `bypass_actors`: the repository owner, and nobody else

The file now carries exactly one entry, and this is it:

```json
{ "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always" }
```

`RepositoryRole` 5 is the repository admin role. `bypass_mode` is `always`.

**An empty `bypass_actors` list is not a stricter gate. It is the removal of the break-glass
path.** This is the part that reads wrong at review time: an empty list looks like the most
rigorous possible choice, as though nobody has been let off the hook. It changes none of the
rules. Deletion, force-push and the required status checks are enforced exactly the same way with
the owner's bypass present as without it. The only thing the empty list changes is whether anybody
can recover when the gate itself turns out to be wrong — a required context that no workflow
produces, a check wedged by an outage, a revert that has to land now. With no bypass actor the
ruleset applies to the owner too: no push to `main`, no merge, and a required check that never
reports leaves every pull request waiting on a status that will never arrive. Recovery means
opening repository settings and editing or deleting the ruleset by hand, per repository. That
manual sweep is the cost the empty list buys, and it buys no additional protection in exchange.

**`always`, not `pull_request`, and this is a deliberate deviation from CICD-15.** The standard
asks for `bypass_mode: "pull_request"`. Do not apply that here. A bypass scoped to pull requests
only acts *inside* a pull request, which is no use in precisely the situation a bypass exists for:
when the pull request is the thing that is wedged. If a required context never reports, a
`pull_request`-scoped bypass has nothing to act on, and the outcome is indistinguishable from
having no bypass at all. Any change that narrows this entry to `pull_request` should be treated as
reintroducing the lockout.

## What is actually applied right now

Read back from the live API on 2026-08-29 with `gh api repos/ChelseaKR/queer-the-stacks/rulesets`
and `gh api repos/ChelseaKR/queer-the-stacks/rulesets/18752854` (GET only):

| | live ruleset |
|---|---|
| id | `18752854` |
| name | `protect-main` (**not** `main-protection`, the name in this file) |
| enforcement | `active`, created 2026-07-09, updated 2026-08-26 |
| conditions | `refs/heads/main` |
| rules | `non_fast_forward`, `deletion`, `required_status_checks` |
| required contexts | `standards`, `verify` |
| `strict_required_status_checks_policy` | `false` |
| bypass actors | `RepositoryRole:5:always` **and** `User:3114598:pull_request` |
| `current_user_can_bypass` | `always` |

The owner is safe today: `RepositoryRole:5:always` is present live and `current_user_can_bypass`
reads `always`. Two things about that table are still findings.

- **The second bypass actor is an unreviewed widening.** `User:3114598` is the owner herself, so it
  grants nothing she does not already hold through `RepositoryRole:5`, but it is redundant, it is
  scoped `pull_request` (the mode the section above explains is the useless one), and no commit in
  this repository records it being added. A bypass list is the one part of a ruleset that should
  never accumulate entries nobody can account for. Recommended, owner-only, at her discretion:
  drop it and leave the admin role as the single standing bypass.
- **This file and the live ruleset disagree**, in the required-context list, in
  `strict_required_status_checks_policy`, and in the ruleset name. The differences are set out
  below.

## What this file proposes, and how it differs from live

- Blocks force-pushes (`non_fast_forward`) and branch deletion on `main`. **Same as live.**
- Requires four status checks: `verify`, `standards`, `Analyze (python)`, `Analyze (actions)`.
  Live requires two, `standards` and `verify`. So this file proposes adding the two CodeQL matrix
  contexts and requires everything live already requires.
- Sets `strict_required_status_checks_policy: true`, meaning a branch must be up to date with
  `main` before it can merge. **Live has this `false`.** This is a genuine proposal, not a
  transcription error, and it is a stricter setting than what is applied; it is safe to propose
  because the owner's `always` bypass survives it.
- **Does not** require pull-request review approval — this is a single-maintainer repo
  (`SECURITY.md` / `README.md`), so a mandatory second reviewer is not meaningful today. Add a
  `pull_request` rule here if that changes.

## Required contexts: only checks that report on every pull request

A required status check that no workflow produces does not fail a pull request, it *suspends* one.
The check sits at "Expected — waiting for status to be reported" and the merge button never
un-greys, for the life of the branch. A path-filtered workflow has the same effect on any pull
request that touches none of its paths, because the workflow is never triggered and therefore
files no check run at all. Every context named in this file was checked against
`.github/workflows/` and against real check runs before being listed. A job's check-run name is
its `name:` if it has one and its job id otherwise, and a matrix job files one check run per
combination.

| context | produced by | trigger | required here |
|---|---|---|---|
| `verify` | `ci.yml`, job `verify` | `pull_request: branches: [main]`, no path filter | yes |
| `standards` | `standards.yml`, job `standards` | `pull_request`, no branch or path filter | yes |
| `Analyze (python)` | `codeql.yml`, job `analyze`, matrix `language: python` | `pull_request: branches: [main]`, no path filter | yes |
| `Analyze (actions)` | `codeql.yml`, job `analyze`, matrix `language: actions` | `pull_request: branches: [main]`, no path filter | yes |
| `trivy` | `container-scan.yml`, job `trivy` | `pull_request: branches: [main]`, **path-filtered** | **no — removed** |
| `zizmor` | `zizmor.yml`, job `zizmor` | `pull_request: branches: [main]`, **path-filtered** | no, and must not be added |
| `scorecard` | `scorecard.yml`, job `analysis` | no `pull_request` trigger at all | no, and must not be added |

**`trivy` was listed as required by the previous version of this file and has been removed.** It is
not a phantom — the job exists and passes — but `container-scan.yml` only runs when a pull request
touches `Dockerfile`, `.dockerignore`, `pyproject.toml`, `uv.lock`, or the workflow itself. On any
other pull request it files no check run. This is observable rather than inferred: PR #89 touched
`Dockerfile` and `uv.lock` and produced a `trivy` check run; PR #79 touched neither and produced
`Analyze (actions)`, `Analyze (python)`, `CodeQL`, `standards` and `verify`, and no `trivy`. Had
`trivy` been required, PR #79 could never have merged. Requiring a path-filtered check is a slow
version of the same mistake as the empty bypass list: it looks stricter and it wedges the
repository.

`standards` reports on forked pull requests too. GitHub withholds repository secrets from forks, so
the deploy-key checkout and the freshness gate are skipped there, but the job still runs and still
files its check run, so requiring it does not wedge a fork's pull request.

## To make it live (manual, owner-only — not done by any remediation pass)

Applying a ruleset is a live GitHub-settings change and is out of scope for an automated pass.
Read the two warnings first.

**POST adds a ruleset. It does not replace one.** There is already a ruleset over `main`
(`protect-main`, id 18752854). Posting this file creates a *second* one, and GitHub evaluates every
ruleset targeting a ref together: the required-context lists union, and the strictest setting wins.
Two rulesets over `main` is a configuration nobody is reading as a whole, and untangling it later
means remembering that both exist. Update the existing ruleset, or delete it first, rather than
posting alongside it.

**Never post a ruleset without reading its `bypass_actors` first.** Check the file you are about to
send, not the file you remember writing:

```sh
jq '.bypass_actors' .github/rulesets/main.proposed.json
# must print exactly:
# [ { "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always" } ]
```

To update the ruleset that already exists, in place, keeping its id and its history:

```sh
gh api --method PUT repos/ChelseaKR/queer-the-stacks/rulesets/18752854 \
  --input .github/rulesets/main.proposed.json
```

Note that this also renames the live ruleset from `protect-main` to `main-protection`, since the
name travels in the body. Change `"name"` in the file to `protect-main` first if you would rather
keep the live name.

To create a new one instead, which is only correct if you have already deleted 18752854:

```sh
gh api --method POST repos/ChelseaKR/queer-the-stacks/rulesets \
  --input .github/rulesets/main.proposed.json
```

Afterwards, confirm the bypass survived the round trip before you close the tab:

```sh
gh api repos/ChelseaKR/queer-the-stacks/rulesets/18752854 \
  --jq '{bypass: .bypass_actors, can_bypass: .current_user_can_bypass}'
```

`current_user_can_bypass` must read `always`. If it reads `never` or `pull_requests_only`, fix it
now, from the browser if the API is what is wedged: **Settings → Rules → Rulesets → protect-main →
Bypass list**.

Once the file and the live ruleset agree, rename this file to `main.json` (drop `.proposed`) in a
follow-up commit, so the committed artifact matches reality.

## What keeps this file honest

`tests/test_ruleset.py` fails if the owner's bypass is removed, emptied, retyped, narrowed to
`pull_request`, or replaced by a different actor, and fails if this README stops naming the same
actor the file carries. It parses the JSON rather than grepping it, because a truncated file still
contains the literal string `bypass_actors`.
