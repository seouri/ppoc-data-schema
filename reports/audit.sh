#!/usr/bin/env bash
# Audit the repository's reports and the checks that keep them honest.
#
# Eleven steps, ordered cheapest-signal-first. Every one has caught something at
# least once, so none is decorative; the notes below say what each is for.
#
#   ./reports/audit.sh              full run
#   ./reports/audit.sh --quick      skip the four-minute full test suite
#   AUDIT_RUNS=6 ./reports/audit.sh raise the determinism sample
#
# Exits non-zero if any step fails, so it is usable as a gate.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
OUT=reports/ppoc-eda
BUNDLE=${PPOC_DUCKDB:-/Users/joon/src/tries/ppoc-duckdb-real/ppoc.duckdb}

#: How many independent rebuilds to compare against the committed content.
#: Parallel aggregation in DuckDB has produced drift that appeared in roughly one
#: build in six, so this is a sampling check rather than a proof; raise it after
#: adding probes that introduce new aggregates.
RUNS=${AUDIT_RUNS:-2}
QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

# md5 on macOS, md5sum elsewhere.
if command -v md5 >/dev/null 2>&1; then hashes() { md5 -q "$@"; }
else hashes() { md5sum "$@" | cut -d" " -f1; }; fi

FAILED=()
step() { printf '\n--- %s ---\n' "$1"; }
ok()   { printf '  %s\n' "$1"; }
bad()  { printf '  FAIL: %s\n' "$1"; FAILED+=("$1"); }
check() { if [ "$1" -eq 0 ]; then ok "$2"; else bad "$2"; fi; }

# The forced rebuild in step 3 dirties the outputs; always put them back.
restore() { git checkout -- "$OUT" 2>/dev/null || true; }
trap restore EXIT

printf '############ report audit ############\n'

step "0. starting state"
STATE_BEFORE=$(git status --porcelain)
if [ -z "$STATE_BEFORE" ]; then ok "tree clean"
else printf '  note: tree is dirty, later steps compare against uncommitted content\n'
     git status --porcelain | sed 's/^/    /'; fi
git fetch -q origin 2>/dev/null || true
ok "$(git status -sb | head -1)"
ok "$(git log --oneline -1)"

if [ ! -f "$BUNDLE" ]; then
  step "1-3. determinism"
  ok "skipped: no DuckDB bundle at $BUNDLE"
else
  step "1. determinism: $RUNS independent computations vs committed content"
  # The build recomputes everything and rewrites only on a difference, so a run
  # that reports "unchanged" is a full computation that matched what is committed.
  for i in $(seq 1 "$RUNS"); do
    line=$("$PY" reports/build_ppoc_eda.py 2>&1 | head -1)
    case "$line" in
      *"findings unchanged"*) ok "run $i: $line" ;;
      *) bad "run $i rebuilt: $line" ;;
    esac
  done

  step "2. tree after the rebuilds"
  if [ -z "$(git status --porcelain -- "$OUT")" ]; then ok "clean — nothing rewritten"
  else bad "the build rewrote its outputs"; git status --porcelain -- "$OUT" | sed 's/^/    /'; fi

  step "3. rendered artifacts byte-stable under a forced rebuild"
  # Step 1 only compares findings, so a non-deterministic renderer would pass it.
  before=$(hashes "$OUT/index.html" "$OUT/ppoc-eda.md" "$OUT/ppoc-eda.pdf" 2>/dev/null)
  "$PY" reports/build_ppoc_eda.py --force >/dev/null 2>&1
  after=$(hashes "$OUT/index.html" "$OUT/ppoc-eda.md" "$OUT/ppoc-eda.pdf" 2>/dev/null)
  [ "$before" = "$after" ]
  check $? "html, markdown and pdf byte-identical"
  restore
fi

step "4. coverage and quoted figures"
"$PY" reports/audit_coverage.py > /tmp/audit_cov.txt 2>&1
cov=$?
head -1 /tmp/audit_cov.txt | sed 's/^/  /'
grep -E 'not quoted|UNBACKED|MISSING' /tmp/audit_cov.txt | sed 's/^/  /' \
  || ok "none unbacked, dead, or missing"
check $cov "$(tail -1 /tmp/audit_cov.txt)"

step "5. report audits (neutrality, disclosure, pdf, ordering)"
"$PY" -m pytest tests/report -q > /tmp/audit_rep.txt 2>&1
check $? "$(tail -1 /tmp/audit_rep.txt)"

step "6. repo-wide lint"
"$PY" -m ruff check . > /tmp/audit_lint.txt 2>&1
check $? "$(tail -1 /tmp/audit_lint.txt)"

step "7. vendored augmenter still byte-identical to its manifest"
"$PY" -m pytest tests/test_augment_import.py -q > /tmp/audit_vend.txt 2>&1
check $? "$(tail -1 /tmp/audit_vend.txt)"

step "8. descriptor"
python3 schema/build.py --check > /tmp/audit_desc.txt 2>&1
check $? "$(tail -1 /tmp/audit_desc.txt)"

step "9. documentation links"
"$PY" - <<'PYEOF'
import pathlib, re, sys
bad = []
for name, base in (("README.md", "."),
                   ("docs/data_description.md", "docs"),
                   ("reports/growth-chart-literacy-real-data-eda.md", "reports")):
    for _, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)",
                                pathlib.Path(name).read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "#")):
            continue
        if not (pathlib.Path(base) / target).exists() \
           and not pathlib.Path(target).exists():
            bad.append(f"{name} -> {target}")
print("  broken:", bad or "none")
sys.exit(1 if bad else 0)
PYEOF
check $? "relative links resolve"

if [ "$QUICK" -eq 1 ]; then
  step "10. full test suite"
  ok "skipped by --quick"
else
  step "10. full test suite"
  "$PY" -m pytest -q > /tmp/audit_all.txt 2>&1
  check $? "$(tail -1 /tmp/audit_all.txt)"
fi

step "11. final state"
restore
STATE_AFTER=$(git status --porcelain)
if [ "$STATE_AFTER" = "$STATE_BEFORE" ]; then
  [ -z "$STATE_AFTER" ] && ok "tree clean" || ok "tree unchanged by the audit"
else
  bad "the audit changed the working tree"
  diff <(printf '%s\n' "$STATE_BEFORE") <(printf '%s\n' "$STATE_AFTER") | sed 's/^/    /'
fi
ok "ahead $(git rev-list --count origin/main..main 2>/dev/null || echo '?'), behind $(git rev-list --count main..origin/main 2>/dev/null || echo '?')"

printf '\n############ result ############\n'
if [ ${#FAILED[@]} -eq 0 ]; then
  printf '  PASS — every step clean\n'
  exit 0
fi
printf '  FAIL — %d step(s):\n' "${#FAILED[@]}"
printf '    %s\n' "${FAILED[@]}"
exit 1
