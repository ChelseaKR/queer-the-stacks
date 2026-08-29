# Open pull request triage — 2026-08-28

Nine open PRs, read against `origin/main` at `66ee334`.

> ## Update — 2026-08-29: #89 landed, as a squash
>
> The body below was written while `origin/main` was still at `66ee334` and #89
> was open. It is kept as written, because its predictions are what happened.
> Read it as an as-of record; this block is the current state.
>
> **#89 merged at `2026-08-29T00:45:38Z` as a squash**, merge commit
> `2ac9d24`. `origin/main` is now `2ac9d24`.
>
> Consequences, each re-verified against `2ac9d24` rather than carried over:
>
> - **`main` is no longer red.** `osv-scanner --lockfile=<origin/main uv.lock>`
>   exits **0**, "No issues found". The same scanner against the `66ee334`
>   lockfile still exits **1** on PYSEC-2026-3721, so the gate has not stopped
>   looking; the tree moved. `main`'s `uv.lock` now pins `pip 26.2.1`, and that
>   blob is **byte-identical** to the one on #82's head.
> - **The advisory is real and still current.** OSV records PYSEC-2026-3721
>   (alias CVE-2026-13346) as published 2026-07-29, last modified 2026-08-21,
>   **not withdrawn**, CVSS 6.5, affecting `pip < 26.2`.
> - **The squash path is the one that happened**, so #82 through #88 are all
>   still open, exactly as the "auto-closing" section predicted. They now need
>   closing by hand.
> - **#82 merged into `main` is provably a no-op.**
>   `git merge-tree --write-tree 2ac9d24 3b3a1b4` returns tree
>   `61aae0ed15efe3e58a939e057e789f5dfea96f70`, which *is* `2ac9d24`'s tree.
>   An empty diff.
> - **#83 through #88 are byte-identical to `main` on every non-CHANGELOG
>   file**, compared blob hash by blob hash, with exactly one exception below.
>
> ### The one exception: do not resolve #86, #87 or #88 toward the PR
>
> `tests/test_a11y.py` differs from `main` on **three** of the branches, and
> **`main` is the newer side** in every case. #89 extracted the Makefile `:=`
> expander into `tests/makefilevars.py` (present on `main`, absent on all three
> branches); `main`'s `tests/test_a11y.py` imports `makefile_list,
> makefile_variables` from it, while the branches still carry the inlined
> `_makefile_variables` helper that predates the extraction.
>
> Blob identities, which is why this is not a judgement call:
>
> | Ref | `tests/test_a11y.py` |
> | --- | --- |
> | `66ee334` (the old common base) | `4a59231` |
> | `main` (`2ac9d24`) | `d526d83` — **newest**, imports `tests.makefilevars` |
> | #86, #87 and #88 heads | `ec2d168` — inlined helper, superseded |
>
> #87 and #88 do not *touch* the file in their own diffs, so a per-PR file
> listing makes them look clean; they inherit `ec2d168` from #86 further down
> the stack. Taking any of their sides deletes the import and re-inlines the
> helper, reverting the refactor. **Close all three; do not merge them and do
> not "resolve" this file toward the PR.**
>
> ### "CLEAN" on #83 through #88 is measured against the wrong base
>
> GitHub reports #83 through #88 as `CLEAN`. That is computed against each PR's
> **own base branch**, which is the PR below it in the stack, not against
> `main`. Merged into `main` they are not clean at all:
>
> | PR | `git merge-tree --write-tree 2ac9d24 <head>` |
> | --- | --- |
> | #82 | tree `61aae0ed` == `main`'s tree. **Empty diff, a true no-op.** |
> | #83, #84, #85 | **CONFLICT** in `CHANGELOG.md` |
> | #86, #87 | **CONFLICT** in `CHANGELOG.md` *and* `tests/test_a11y.py` |
> | #88 | **CONFLICT** in `tests/test_a11y.py` |
>
> The content is all landed; the conflicts are the squash's rewritten history
> meeting the branches' stale copies. This is another reason the disposition is
> *close*, not *retarget and merge*.
>
> ### Closing hazard: the stack is chained
>
> #82 through #88 are a linear chain, each PR based on the branch below it.
> **Close them individually, and do not pass `--delete-branch`.** Each PR's head
> branch *is* the next PR's base, so deleting one removes the branch the next PR
> is measured against, and GitHub reacts by retargeting or auto-closing the
> child. Either way the action propagates down a chain of six, and a retargeted
> child lands on `main` in the conflicting state tabulated above rather than the
> clean one it shows today.
>
> `delete_branch_on_merge` is `false` on this repository, so nothing deletes a
> branch unless it is asked to. Do not ask.

## The one thing to know first

*(As of 2026-08-28, superseded by the update block above.)*

`origin/main` has not moved since **2026-08-19**. Nothing landed today. If you
are reading a local checkout and it looks like the gate-falsifiability work is
already on `main`, that is because the working tree is checked out on
`fix/local-gates-fail-loudly`, which is PR #89's head branch and is *not*
merged. Every staleness judgement below is measured against `66ee334`.

## Group counts

| Group | Count | PRs |
| --- | --- | --- |
| Merge this one; it delivers everything | 1 | #89 |
| Fully contained in #89, close after it lands | 7 | #82, #83, #84, #85, #86, #87, #88 |
| Independent, still wanted, needs a changelog reposition | 1 | #76 |

## Per-PR table

| PR | Base branch | Real merge state | CI, and what the CI actually means | Recommendation |
| --- | --- | --- | --- | --- |
| #89 | `main` | CLEAN, verified by `git merge-tree --write-tree` | All six checks green, including `trivy` and `verify`. Genuine. | **Merge first.** It contains every commit of #82 through #88. |
| #88 | `fix/container-scan-green` | CLEAN, but content is already inside #89 | Only `standards` ran. `verify`, `CodeQL`, `trivy`, `zizmor` are **absent**, not passing. | Close as delivered by #89. |
| #87 | `fix/a11y-page-set-is-checked` | CLEAN, content inside #89 | Same: `standards` only; the rest absent. | Close as delivered by #89. |
| #86 | `fix/csp-covers-what-is-served` | CLEAN, content inside #89 | Same: `standards` only; the rest absent. | Close as delivered by #89. |
| #85 | `fix/privacy-guardrails-can-fail` | CLEAN, content inside #89 | Same: `standards` only; the rest absent. | Close as delivered by #89. |
| #84 | `chore/standards-pin-recorded` | CLEAN, content inside #89 | Same: `standards` only; the rest absent. | Close as delivered by #89. |
| #83 | `chore/lockfile-pip-advisory` | CLEAN, content inside #89 | Same: `standards` only; the rest absent. | Close as delivered by #89. |
| #82 | `main` | UNSTABLE, content inside #89 | `trivy` **fails for a reason that is not its own**: Debian base-image CVEs. | **Do not merge on its own.** See "Merging #82 alone turns `main` red". |
| #76 | `main` | Clean against `main` today, **conflicts once #89 lands** | `trivy` fails for the same base-image reason as #82; everything else green. | Merge **after** #89, repositioning its changelog block by hand. |

## The stack

Six of the nine PRs form one linear chain rooted at `main`, and PR #89 is a
separate PR to `main` whose head contains the entire chain.

```
main (66ee334)
 └─ #82  chore/lockfile-pip-advisory              +8/-3      base: main
     └─ #83  chore/standards-pin-recorded         +154/-0
         └─ #84  fix/privacy-guardrails-can-fail  +427/-93
             └─ #85  fix/csp-covers-what-is-served     +217/-34
                 └─ #86  fix/a11y-page-set-is-checked  +127/-9
                     └─ #87  fix/container-scan-green  +67/-8
                         └─ #88  fix/invariants-asserted-as-equalities  +235/-30

#89  fix/local-gates-fail-loudly   +1948/-197   base: main
     ^ strict descendant of all seven branches above
```

Verified with `git merge-base --is-ancestor`: every one of the seven branches
is an ancestor of `fix/local-gates-fail-loudly`. The cumulative diffs against
`main` climb monotonically and end exactly at #89's totals:

| Branch | Files | vs `main` |
| --- | --- | --- |
| `chore/lockfile-pip-advisory` (#82) | 2 | +8 / -3 |
| `chore/standards-pin-recorded` (#83) | 4 | +162 / -3 |
| `fix/privacy-guardrails-can-fail` (#84) | 9 | +589 / -96 |
| `fix/csp-covers-what-is-served` (#85) | 10 | +806 / -130 |
| `fix/a11y-page-set-is-checked` (#86) | 12 | +933 / -139 |
| `fix/container-scan-green` (#87) | 14 | +1000 / -147 |
| `fix/invariants-asserted-as-equalities` (#88) | 16 | +1235 / -177 |
| `fix/local-gates-fail-loudly` (#89) | 21 | +1948 / -197 |

### What this means for auto-closing, and why the merge button matters

Merging #89 delivers 100 percent of #82 through #88. **Whether that also closes
them depends on which merge method you pick**, and this repository has all three
enabled (`allow_squash_merge`, `allow_merge_commit` and `allow_rebase_merge` are
all true; `delete_branch_on_merge` is false).

- **Merge commit.** The seven branches' commits land on `main` with their
  original SHAs. Their heads become reachable from `main`, and GitHub closes
  #82 through #88 automatically. Nothing to clean up.
- **Squash, which is what every recent merge on `main` used.** The single commit
  that lands shares no SHA with any branch commit, GitHub has nothing to match,
  and all seven stay open showing diffs that have shrunk to nothing. You then
  have to close them by hand.
- **Rebase.** Same problem as squash: the commits are rewritten, so the SHAs do
  not match.

Recent history on `main` is one commit per PR with a trailing `(#nn)`, so the
habit here is squash. **If you want the queue to clean itself up, merge #89 with
a merge commit rather than a squash.** That is the single choice that turns
seven manual closes into zero.

Either way, note that deleting a merged base branch does not close its children;
GitHub retargets them onto `main`. So merging #82 and deleting its branch would
leave #83 open, retargeted, with its own diff intact.

## `main` was red at `66ee334`, and #89 was the fix

*(Resolved. #89 landed; `main` at `2ac9d24` scans clean. See the update block.)*

`make verify` fails on `origin/main` at `66ee334`, at the `security` stage:

```
Found 1 known vulnerability in 1 package
Name Version ID              Fix Versions
---- ------- --------------- ------------
pip  26.1.2  PYSEC-2026-3721 26.2
make: *** [security] Error 1
```

Run against a clean worktree of `origin/main` with `uv sync --locked`, so this
is `main`'s own state and not a local artifact. It is exactly the advisory #82
was opened to clear, and it confirms #82's description independently of the PR
body.

`main`'s last CI run predates the advisory, which is why `main` looks green on
GitHub while failing locally. The `security` stage is also not what
`container-scan` measures, so this is a second, separate reason `main` is not
actually clean.

Both #82 and #89 carry the `pip` 26.2.1 bump, byte-identical. Merging #89
clears it.

## Merging #82 alone turns `main` red

`container-scan.yml` runs on push to `main` filtered to `Dockerfile`,
`.dockerignore`, `pyproject.toml`, `uv.lock` and its own file. #82 changes
`uv.lock`, so merging it triggers the scan on `main`.

That scan fails today, and not because of anything #82 does. The failure on run
`33138202709` is Debian base-image CVEs: `CVE-2026-14456` in openssl and
`CVE-2026-53612` through `CVE-2026-53615` in util-linux. The last green
container scan on `main` was 2026-08-16; the path filter has kept it from
running since, so `main` is stale-green rather than actually clean.

The fix is in #87, which is inside #89: a new base-image digest, an
`--only-upgrade` of the three OpenSSL packages, and `pip uninstall pip` from the
runtime layer. `trivy` passes on #89 and on nothing else.

**Merge #89 before anything else that touches `Dockerfile`, `uv.lock` or
`pyproject.toml`.**

## Non-diff hazards

### #76 and #89 conflict, in both orders, while both report mergeable

This is the one to watch. Each PR is individually clean against `main`. GitHub
computes each independently and therefore cannot see it.

Simulated by writing the merge tree of the first PR, making a commit from it
with `git commit-tree`, and merge-treeing the second onto that:

```
merge #89, then #76  ->  CONFLICT (content): Merge conflict in CHANGELOG.md
merge #76, then #89  ->  CONFLICT (content): Merge conflict in CHANGELOG.md
```

Both add a block immediately after the same `## [Unreleased]` preamble anchor.
Whichever lands second needs its changelog block repositioned by hand. Nothing
else in either PR conflicts.

`Dockerfile` and `README.md` auto-merge, and the auto-merged `Dockerfile` is
**semantically correct**: it keeps #89's new base digest and OpenSSL stanza and
#76's `uv export --locked`. Checked by reading the merged blob, not by trusting
the exit status.

### The changelog-inside-a-released-section hazard does not exist here

Checked and absent. `CHANGELOG.md` has exactly one `## ` heading,
`## [Unreleased]` at line 9, and the file is 302 lines. No release has been
tagged. Every hunk in every open PR lands inside Unreleased because there is
nowhere else to land. Re-check this once `v0.1.0` is cut.

### #76 arms a gate that then has to pass, and it does

#76 turns `uv sync --frozen` into `uv sync --locked` in `ci.yml` and
`uv export --frozen` into `--locked` in the `Dockerfile`, on the correct
grounds that `--frozen` never reads `pyproject.toml` and so exits 0 on a
drifted lock. That is a real non-gate, and #89 does **not** fix it: #89 leaves
`uv export --frozen` in place. The two are complementary, and #76 is still
wanted after #89 lands.

The risk is that arming the gate makes it fail. It does not: `uv lock --check`
against #89's `pyproject.toml` and `uv.lock` resolves 84 packages clean.
Verified by running it.

### Generated files: checked, and they hold

`docs/audits/coverage.xml` is committed generated output, and #89 changes it.
The change is the `timestamp` attribute and nothing else: `lines-valid`,
`lines-covered`, `line-rate`, `branches-valid`, `branches-covered` and
`branch-rate` are byte-identical to `main`.

That looks wrong for a PR adding roughly 1,100 lines of tests and 22 lines to
`app/build_static.py`, so it was checked rather than assumed. It is correct.
`[tool.coverage.run]` omits `app/build_static.py` explicitly, and the report's
`<source>` roots are `app`, `ingest` and `recommender` only. Test files are not
in the denominator. Nothing #89 changes is measured, so the totals genuinely do
not move.

One unrelated observation: `coverage.xml` embeds absolute paths under
`/Users/chelsea/portfolio/queer-the-stacks/`. That is pre-existing on `main`,
not something any open PR introduces.

## Defect hunt

The brief for this sweep was to find tests that pass in both the fixed and the
unfixed state. In this queue #89 is the *cure* for that class rather than a
carrier of it, and the claim was checked rather than taken from the PR body.

- `tests/test_gate_lists.py::test_every_marker_root_exists_and_holds_python`
  asserts `any(directory.rglob("*.py"))` for each scanned root. That is a
  direct guard against a glob that matches nothing and against an `rglob` over
  a renamed directory.
- `_first_party_packages()` and `_first_party_roots()` derive the module set
  from `pyproject.toml` instead of listing it. That is a direct guard against a
  hardcoded member list standing in for "all modules".
- `test_coverage_floor_is_still_enforced` asserts exactly one
  `--cov-fail-under`, so a second one cannot silently override the floor.
- `scripts/secret-scan.sh` checks every pattern against a known-positive sample
  before it scans anything, and exits 1 if a pattern stops matching its own
  sample. A pattern edited into something inert now fails loudly instead of
  reporting zero findings.

The secret-scan rewrite in #89 is worth reading in full. It documents four ways
the old fallback reported success having read nothing, and one of them is
exactly the "scanner whose default ignore drops half its stated scope" shape:
the old file list was six extension globs, `*.py *.toml *.yml *.yaml *.sh *.md`,
so an AWS key id in a `.json` scanned clean. It now scans every tracked file and
relies on `grep -I` to skip binaries.

### CI green on #83 through #88 is vacuous

Not a defect in any PR, but it changes how much the queue's green means.
`ci.yml`, `codeql.yml`, `container-scan.yml` and `zizmor.yml` all declare
`pull_request: branches: [main]`. `standards.yml` declares a bare
`pull_request:` with no branch filter.

So a PR whose base is another PR's branch runs `standards` and nothing else.
#83 through #88 each show a single green check and a CLEAN merge state. They
have not been type-checked, tested, scanned for CVEs, or run through CodeQL.
That is **absent** CI, not passing CI, and it is why merging the stack
bottom-up would be merging six untested PRs.

## Safe order of operations

1. **Merge #89 into `main`, using a merge commit rather than a squash.** It is
   fully green on all six checks, it is the only branch on which `trivy` passes,
   it delivers #82 through #88, and a merge commit makes GitHub close all seven
   of them for you.
2. **Confirm #82 through #88 closed.** If step 1 was squashed instead, they will
   still be open with empty diffs and need closing by hand, noting in each that
   #89 delivered it. Delete their branches only after closing, and expect no
   cascade.
3. **Reposition #76's changelog block, then merge #76.** Its `### Fixed` and
   `### Changed` entries need to move below the ones #89 added under
   `## [Unreleased]`. This is the step that needs a human edit; nothing else in
   the queue does.
4. Confirm `container-scan` is green on `main` after step 1 before merging
   anything else that touches `Dockerfile`, `uv.lock` or `pyproject.toml`.

No merge in this queue needs a regeneration step. `docs/audits/coverage.xml` was
the candidate and it was checked and cleared.

## Verified, versus taken on trust

### Verified here

- `origin/main` is at `66ee334`, dated 2026-08-19, and nothing landed today.
  The local working tree is on `fix/local-gates-fail-loudly`.
- `make verify` fails on a clean `origin/main` worktree at the `security` stage
  on PYSEC-2026-3721, run locally after `uv sync --locked`.
- All seven stack branches are strict ancestors of #89's head
  (`git merge-base --is-ancestor`, all seven YES).
- The cumulative diff totals in the stack table, from `git diff --shortstat`.
- Workflow trigger filters, read from the five workflow files, and therefore
  the "absent CI" classification for #83 through #88.
- #82's `trivy` failure is base-image CVEs, read from the failing job log of run
  `33138202709`.
- `container-scan` last ran green on `main` on 2026-08-16, from `gh run list`.
- The #76-plus-#89 `CHANGELOG.md` conflict, in both orders, simulated with
  `git merge-tree --write-tree` plus `git commit-tree`.
- The merged `Dockerfile` keeps both PRs' intent, read from the merged blob.
- `CHANGELOG.md` has exactly one section heading, so no hunk can land in a
  released section.
- `uv lock --check` resolves clean against #89's manifest and lock.
- `coverage.xml`'s unchanged totals are correct, from `[tool.coverage.run]`'s
  omit list and the report's `<source>` roots.
- #89's `uv.lock` change is byte-identical to #82's.
- Defect-shape guards in `tests/test_gate_lists.py`, read directly.
- Repository merge settings, from the repository API: squash, merge commit and
  rebase all enabled, `delete_branch_on_merge` false.

### Taken on trust

- That #89's individual gate fixes each do what their commit messages say when
  executed in CI. The six checks are green on the PR, and the tests were read,
  but the gates were not each broken deliberately to confirm each one fails.
  The secret-scan self-test makes that class of check self-verifying; the a11y
  and CSP gates were not re-run locally.
- The experiment write-ups in the `secret-scan.sh` header, for example the
  6001-file two-batch `xargs` reproduction. The reasoning is sound and the code
  matches it, but those experiments were not repeated.
- Trivy's finding set on #89 being genuinely zero rather than suppressed. The
  job passed; its configuration was not audited for added ignore rules.
- `standards` check content. It passes everywhere, including on PRs with no
  other coverage, and was not examined.

## A note on how this report was pushed

An earlier draft of this section recorded a plan to push with `--no-verify`,
on the reasoning that the branch was `66ee334` plus one Markdown file and so
inherited that commit's failing `security` stage, which no change here could
clear. That reasoning was sound and its conclusion is now moot.

#89 landed the `pip 26.2.1` bump onto `main` before this branch was ever
pushed, so the branch was **rebased onto `2ac9d24`** instead. The advisory is
cleared by the commit that was always meant to clear it, no redundant bump was
invented, and the pre-push hook's `make verify` was run in full and passed on
its own. Nothing was waived and no escape hatch was used.
