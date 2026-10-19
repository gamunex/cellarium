#!/bin/sh
# Baut die Projektseite (site/ + Oberfläche als Demo unter demo/) und schiebt sie in den Branch gh-pages.
set -eu
cd "$(dirname "$0")/.."
tmp=$(mktemp -d)
trap 'git worktree remove --force "$tmp" 2>/dev/null || true; rm -rf "$tmp"' EXIT
if git show-ref --quiet refs/heads/gh-pages || git fetch -q origin gh-pages:gh-pages 2>/dev/null; then
    git worktree add -q "$tmp" gh-pages
else
    git worktree add -q --detach "$tmp"
    git -C "$tmp" checkout -q --orphan gh-pages
fi
git -C "$tmp" rm -rfq --ignore-unmatch . >/dev/null
mkdir -p "$tmp/demo"
cp -r site/. "$tmp/"
cp -r cellarium/web/. "$tmp/demo/"
touch "$tmp/.nojekyll"
git -C "$tmp" add -A
if git -C "$tmp" diff --cached --quiet; then
    echo "Seite unverändert."
else
    git -C "$tmp" commit -qm "Seite aus $(git rev-parse --short HEAD)"
    git -C "$tmp" push -q origin gh-pages
    echo "Seite veröffentlicht: https://gamunex.github.io/cellarium/"
fi
