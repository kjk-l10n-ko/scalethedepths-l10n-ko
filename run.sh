#!/usr/bin/env bash
# Game repo wrapper: runs tools-l10n-ko tools in Docker.
# Reads pipeline_repo and pipeline_ref from game.toml.
# Usage: ./run.sh <command...>
#   ./run.sh python -m adapters.jetlancer migrate --src ... --out ...
#   ./run.sh bash
set -euo pipefail
S="$(cd "$(dirname "$0")" && pwd)"
C="$S/game.toml"
PR="${PIPELINE_REPO:-$(grep -oP 'pipeline_repo\s*=\s*"\K[^"]+' "$C" 2>/dev/null || true)}"
PF="${PIPELINE_REF:-$(grep -oP 'pipeline_ref\s*=\s*"\K[^"]+' "$C" 2>/dev/null || echo main)}"
if [ -n "${DEV:-}" ] && [ -n "$PR" ]; then
  B="$PR"; SHA="dev"; DM="-v ${PR}/tools:/opt/tr/tools -v ${PR}/adapters:/opt/tr/adapters"
else
  CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/l10n-ko/tools-l10n-ko"
  [ -d "$CACHE/.git" ] || git clone "$PR" "$CACHE"
  git -C "$CACHE" fetch --tags --force origin
  SHA="$(git -C "$CACHE" rev-parse --short=12 "${PF}^{commit}")"
  EXPORT="${CACHE}/export-${SHA}"
  if [ ! -d "$EXPORT" ]; then mkdir -p "$EXPORT"; git -C "$CACHE" archive --format=tar "$PF" | tar xf - -C "$EXPORT"; fi
  B="$EXPORT"; DM=""
fi
IMG="l10n-ko-patch:${SHA}"
docker image inspect "$IMG" >/dev/null 2>&1 || docker build -t "$IMG" -f "$B/docker/patch/Dockerfile" "$B"
TTY=""; [ -t 0 ] && TTY="-t"
exec docker run --rm -i ${TTY} --user "$(id -u):$(id -g)" \
  -v "$S:/work" ${DM} \
  "$IMG" "${@:-bash}"
