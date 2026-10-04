#!/usr/bin/env bash
# Install omarchy-clean from a source checkout. Run as your normal user; sudo is used for system files only.
set -euo pipefail

PREFIX="${PREFIX:-/usr/local}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGES=(python-evdev hyprpolkitagent python-gobject gtk4 gtk4-layer-shell polkit)

user_only=0
setup_args=()
for arg in "$@"; do
    case "$arg" in
        --user-only) user_only=1 ;;
        --no-keybind) setup_args+=("$arg") ;;
        -h|--help) echo "usage: install.sh [--user-only] [--no-keybind]"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [ "$EUID" -eq 0 ]; then
    echo "Run install.sh as your normal user, not root." >&2
    exit 1
fi

missing=()
for pkg in "${PACKAGES[@]}"; do
    pacman -Q "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if [ "${#missing[@]}" -gt 0 ]; then
    echo "Missing packages. Install them first with:" >&2
    echo "  sudo pacman -S ${missing[*]}" >&2
    exit 1
fi

[ "$user_only" -eq 1 ] || sudo make -C "$SRC_DIR" install PREFIX="$PREFIX"
"$SRC_DIR/bin/omarchy-clean-setup" "${setup_args[@]}"
echo "omarchy-clean installed."
