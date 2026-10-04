#!/usr/bin/env bash
# Remove omarchy-clean. Run as your normal user; sudo is used for system files only.
set -euo pipefail

PREFIX="${PREFIX:-/usr/local}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

"$SRC_DIR/bin/omarchy-clean-setup" --remove
[ "$user_only" -eq 1 ] || sudo make -C "$SRC_DIR" uninstall PREFIX="$PREFIX"
echo "omarchy-clean removed."
