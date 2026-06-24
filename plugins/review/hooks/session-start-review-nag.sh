#!/usr/bin/env bash
# SessionStart — lists pending review markers so the user knows a review-triggering
# action completed without a reviewer-personas review completion token.
set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
PENDING_DIR="$PROJECT_DIR/.claude/reviews/pending"

[ -d "$PENDING_DIR" ] || exit 0

markers=()
while IFS= read -r -d '' f; do
    markers+=("$f")
done < <(find "$PENDING_DIR" -maxdepth 1 -name '*.marker' -print0 2>/dev/null || true)

[ ${#markers[@]} -eq 0 ] && exit 0

echo ""
echo "Artifacts created or modified without a reviewer-personas review token:"
for m in "${markers[@]}"; do
    content=$(cat "$m" 2>/dev/null || echo "$(basename "$m" .marker)")
    slug=$(basename "$m" .marker)
    echo "  - $content"
    echo "    Fix: use the reviewer-personas skill (review:reviewer-personas), then write .claude/reviews/completed/${slug}.json"
done
echo ""
exit 0
