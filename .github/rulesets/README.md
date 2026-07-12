# Branch-protection ruleset — committed artifact (CICD-12)

`main.proposed.json` is the **proposed** ruleset for the `main` branch, committed as the artifact
`STANDARDS/CI-CD-STANDARD.md` (CICD-12) asks for. The `.proposed` suffix is deliberate and load-
bearing: as of 2026-07-05, **no branch protection or ruleset is actually active** on this repo —
verified independently via `gh api repos/ChelseaKR/queer-the-stacks/branches/main/protection`
(404 "Branch not protected") and OpenSSF Scorecard's Branch-Protection check (0/10, see
`docs/audits/scorecard-2026-07.md`). Committing a file named `main.json` without the `.proposed`
marker would misrepresent it as the live configuration.

## What it does

- Blocks force-pushes and branch deletion on `main`.
- Requires the `ci` workflow (`verify` job), both `codeql` matrix jobs, and the container Trivy
  scan to pass before a merge (once those checks have run at least once on the branch, so GitHub
  can recognize the context names — the exact strings above are set from this pass's workflow job
  names and may need adjusting after the first real run).
- **Does not** require PR review approval — this is a single-maintainer repo
  (`SECURITY.md`/`README.md`), so a mandatory second reviewer isn't meaningful today. Add a
  `pull_request` rule here if that changes.

## To make it live (manual action — not done by this remediation pass)

Applying a ruleset is a live GitHub-settings change and is out of scope for an automated
remediation pass (see the ground rules in the 2026-07-05 execution log). To apply it yourself:

```sh
gh api --method POST repos/ChelseaKR/queer-the-stacks/rulesets \
  --input .github/rulesets/main.proposed.json
```

Or paste the JSON's contents into **Settings → Rules → Rulesets → New branch ruleset → Import** in
the GitHub UI. After it's live and confirmed working, rename the file to `main.json` (drop
`.proposed`) in a follow-up commit so the committed artifact matches reality again.
