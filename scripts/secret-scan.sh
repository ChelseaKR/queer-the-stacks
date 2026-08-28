#!/usr/bin/env bash
# Secret scan: runs gitleaks if it's on PATH, else falls back to a high-signal
# grep. CI installs a pinned, checksum-verified gitleaks binary before this
# script runs (see .github/workflows/ci.yml), so CI always takes the gitleaks
# path; a local `make security` without gitleaks installed takes the grep
# fallback, which is a weaker but still merge-blocking approximation.
#
# Three ways the fallback used to report success having found nothing because
# it looked at nothing, all fixed below:
#
#   1. `git ls-files ... || true` outside a git work tree (or with git absent)
#      left the file list empty, and the next line printed
#      "no tracked files yet — ok" and exited 0. Verified by copying this
#      script into a non-repository directory and running it.
#   2. The file list was six globs: *.py *.toml *.yml *.yaml *.sh *.md. An AWS
#      key id in a .json, a Dockerfile, a Makefile, or a .js file was not
#      scanned. Verified with a planted AKIA... key in a tracked .json.
#   3. `echo "$files" | xargs grep` splits into batches once the argument list
#      is long enough, and `if xargs ...` then sees only the *last* batch's
#      exit status, so a match in an earlier batch could be dropped.
#   4. The private-key pattern begins with `-`, so `grep -InE "$pat"` parsed it
#      as a bundle of options. grep printed "unrecognized option" to stderr,
#      which `2>/dev/null` discarded, and exited non-zero, which the `if` read
#      as "no match". That pattern has therefore never matched anything.
#      Verified against origin/main: a committed PEM private-key block in a
#      tracked .md file produced "secret-scan: 0 findings" and exit 0. Every
#      grep below passes its pattern after `-e`. (This comment deliberately
#      describes the header rather than quoting it: the scan reads this file
#      too, and a literal would make it report itself forever.)
#
# The scan now covers every tracked file, refuses to run on an empty list, and
# decides on captured output rather than on a batched exit status. It also
# checks each pattern against a known-positive sample before scanning, so a
# pattern edited into something that matches nothing fails loudly instead of
# reporting zero findings.
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

count=$(git ls-files | wc -l | tr -d ' ')
if [ "$count" -eq 0 ]; then
  echo "secret-scan: no tracked files to scan — refusing to report success" >&2
  exit 1
fi

found=0
for pat in "${patterns[@]}"; do
  # Captured, not piped into `if`: xargs batches a long file list, and only the
  # final batch's exit status would reach the conditional.
  hits=$(git ls-files -z | xargs -0 grep -InE -e "$pat" 2>/dev/null || true)
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
