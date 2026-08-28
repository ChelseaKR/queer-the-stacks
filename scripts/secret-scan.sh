#!/usr/bin/env bash
# Secret scan: runs gitleaks if it's on PATH, else falls back to a high-signal
# grep. CI installs a pinned, checksum-verified gitleaks binary before this
# script runs (see .github/workflows/ci.yml), so CI always takes the gitleaks
# path; a local `make security` without gitleaks installed takes the grep
# fallback, which is a weaker but still merge-blocking approximation.
#
# The fallback had four ways to report success having read nothing, or having
# thrown away what it did read. Each is stated with the experiment that
# demonstrated it, run against the pre-fix script on macOS (BSD grep 2.6.0,
# BSD xargs):
#
#   1. `git ls-files ... || true` left the file list empty outside a git work
#      tree, and the next line printed "no tracked files yet — ok" and exited 0.
#      Verified: the old script, run in a non-repository directory holding a
#      file with an AWS key id in it, printed exactly that and exited 0.
#   2. The file list was six globs: *.py *.toml *.yml *.yaml *.sh *.md. Nothing
#      with any other extension was read. Verified: an AWS key id committed in
#      a .json produced "secret-scan: 0 findings" and exit 0.
#   3. `if echo "$files" | xargs grep ...` decided on xargs' exit status. Once
#      the argument list exceeds ARG_MAX, xargs splits it and runs grep once
#      per batch, and exits non-zero if *any* batch did. A run where some
#      batches match and some do not is therefore read as "no match" — and note
#      it is not, as the shape suggests, the last batch's status that survives:
#      a first batch that matched is lost just as surely as a last one.
#      Verified: a repository of 6001 tracked files (two batches) holding one
#      AWS key id printed the offending line and then said "secret-scan: 0
#      findings" and exited 0.
#   4. The private-key pattern begins with `-`, so `grep -InE "$pat"` parsed it
#      as an option bundle. grep printed "unrecognized option" and exited 2;
#      `2>/dev/null` hid the message and the `if` read the non-zero status as
#      "no match", so that pattern had never matched anything. Verified: a PEM
#      private-key block committed in a tracked .md produced "secret-scan: 0
#      findings" and exit 0, and that pattern under `grep -InE` exits 2 while
#      the same pattern after `-e` exits 0 and prints the line. Every grep
#      below passes its pattern after `-e`. (This comment describes the header
#      rather than quoting it: the scan reads this file too, and a literal
#      would make it report itself forever.)
#
# A fifth belonged to the first draft of this fix, and is removed here.
# `hits=$(... 2>/dev/null || true)` discarded grep's stderr *and* its exit
# status, so a file the scan could not read counted as a file with no secret in
# it — defect 4 again, one layer down. Verified: with the only secret-bearing
# file chmod 000, that draft printed "secret-scan: 0 findings across 2 tracked
# files" and exited 0. grep's stderr is now captured, and anything on it fails
# the run: a tree the scan could not read in full is a tree it cannot vouch for.
# The likely causes are a tracked file deleted in the working tree and a file
# whose permissions exclude the current user; the message says so.
#
# What the fallback now guarantees: it reads every tracked file, it refuses to
# run on a list it could not build or that came back empty, it decides on
# captured output rather than on a batched exit status, and it fails if any
# part of the tree could not be read. It also checks each pattern against a
# known-positive sample before scanning, so a pattern edited into something
# inert fails loudly instead of quietly reporting zero findings.
set -euo pipefail

if command -v gitleaks >/dev/null 2>&1; then
  exec gitleaks detect --no-banner --redact
fi

# Fallback: grep every tracked file for high-signal secret shapes. `grep -I`
# skips binaries, so there is no reason to restrict the file list by extension.
patterns=(
  'AKIA[0-9A-Z]{16}'                       # AWS access key id
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'     # private keys
  'xox[baprs]-[0-9A-Za-z-]{10,}'           # slack tokens
  'AIza[0-9A-Za-z_\-]{35}'                 # google api key
  '(secret|password|api[_-]?key)[[:space:]]*=[[:space:]]*["'"'"'][^"'"'"']{12,}'
)

# One known-positive per pattern, in the same order. Each is assembled from
# fragments at run time so that no line of this file is itself a match — the
# scan covers this script, and a literal sample here would make it report
# itself forever.
samples=(
  "AKIA$(printf 'A%.0s' {1..16})"
  "-----BEGIN RSA PRIVATE $(printf 'KEY')-----"
  "xox""b-0123456789abcdef"
  "AIza$(printf 'b%.0s' {1..35})"
  "password""=\"correcthorsebatterystaple\""
)

if [ "${#patterns[@]}" -ne "${#samples[@]}" ]; then
  echo "secret-scan: ${#patterns[@]} patterns but ${#samples[@]} samples" >&2
  exit 1
fi

for i in "${!patterns[@]}"; do
  if ! printf '%s\n' "${samples[$i]}" | grep -qIE -e "${patterns[$i]}"; then
    echo "secret-scan: pattern $((i + 1)) no longer matches its own sample;" >&2
    echo "             the scan would report 0 findings whatever the tree holds" >&2
    exit 1
  fi
done

# The file list is built once, checked, and then reused for every pattern, so
# the count reported at the end describes exactly the files that were scanned.
list=$(mktemp)
errs=$(mktemp)
trap 'rm -f "$list" "$errs"' EXIT

if ! git ls-files -z >"$list"; then
  echo "secret-scan: could not list tracked files (not a git work tree?);" >&2
  echo "             refusing to report a clean scan of a tree it never read" >&2
  exit 1
fi

count=$(tr -cd '\0' <"$list" | wc -c | tr -d ' ')
if [ "$count" -eq 0 ]; then
  echo "secret-scan: no tracked files to scan — refusing to report success" >&2
  exit 1
fi

found=0
for pat in "${patterns[@]}"; do
  # Captured, not piped into `if`: xargs batches a long file list, and the
  # conditional would then be reading an aggregate status, not this scan's
  # result. stderr is captured too, and checked below, because a grep that
  # could not read a file exits non-zero exactly as a grep that found nothing
  # does.
  : >"$errs"
  hits=$(xargs -0 grep -InE -e "$pat" <"$list" 2>"$errs" || true)
  if [ -s "$errs" ]; then
    echo "secret-scan: part of the tree could not be read, so a clean result" >&2
    echo "             would mean nothing. A tracked file deleted in the" >&2
    echo "             working tree, or one the current user cannot read," >&2
    echo "             will do this. grep reported:" >&2
    cat "$errs" >&2
    exit 1
  fi
  if [ -n "$hits" ]; then
    printf '%s\n' "$hits"
    found=1
  fi
done

if [ "$found" -ne 0 ]; then
  echo "secret-scan: potential secret detected (above)" >&2
  exit 1
fi
echo "secret-scan: 0 findings across $count tracked files"
