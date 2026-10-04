#!/usr/bin/env bash
# Remove omarchy-clean. Run as your normal user; sudo is used for system steps only.
set -euo pipefail

PREFIX="${PREFIX:-/usr/local}"
HYPR_CONFIG_DIR="${HYPR_CONFIG_DIR:-$HOME/.config/hypr}"
APPS_DIR="${APPS_DIR:-$HOME/.local/share/applications}"
BEGIN_MARK='-- >>> omarchy-clean >>>'
END_MARK='-- <<< omarchy-clean <<<'

user_only=0
for arg in "$@"; do
    case "$arg" in
        --user-only) user_only=1 ;;
        -h|--help) echo "usage: uninstall.sh [--user-only]"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [ "$EUID" -eq 0 ]; then
    echo "Run uninstall.sh as your normal user, not root." >&2
    exit 1
fi

file="$HYPR_CONFIG_DIR/bindings.lua"
if [ -f "$file" ] && grep -qF -- "$BEGIN_MARK" "$file"; then
    tmp="$(mktemp)"
    awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
        $0 == b { skip = 1; next }
        skip && $0 == e { skip = 0; next }
        !skip { print }
    ' "$file" > "$tmp"
    cat "$tmp" > "$file"
    rm -f "$tmp"
fi

rm -f "$APPS_DIR/omarchy-clean.desktop"

if [ "$user_only" -eq 0 ]; then
    sudo rm -rf "$PREFIX/lib/omarchy-clean"
    sudo rm -f "$PREFIX/bin/omarchy-clean" /usr/share/polkit-1/actions/dev.omarchy.clean.policy
fi

if command -v hyprctl >/dev/null 2>&1; then
    hyprctl reload >/dev/null 2>&1 || true
fi
echo "omarchy-clean removed."
echo "Note: hyprpolkitagent.service was left enabled (other apps use it)."
