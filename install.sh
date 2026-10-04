#!/usr/bin/env bash
# Install omarchy-clean. Run as your normal user; sudo is used for system steps only.
set -euo pipefail

PREFIX="${PREFIX:-/usr/local}"
HYPR_CONFIG_DIR="${HYPR_CONFIG_DIR:-$HOME/.config/hypr}"
APPS_DIR="${APPS_DIR:-$HOME/.local/share/applications}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$PREFIX/lib/omarchy-clean"
POLICY_DIR=/usr/share/polkit-1/actions
BEGIN_MARK='-- >>> omarchy-clean >>>'
END_MARK='-- <<< omarchy-clean <<<'
PACKAGES=(python-evdev hyprpolkitagent python-gobject gtk4 gtk4-layer-shell polkit)

user_only=0
keybind=1
for arg in "$@"; do
    case "$arg" in
        --user-only) user_only=1 ;;
        --no-keybind) keybind=0 ;;
        -h|--help) echo "usage: install.sh [--user-only] [--no-keybind]"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [ "$EUID" -eq 0 ]; then
    echo "Run install.sh as your normal user, not root." >&2
    exit 1
fi

validate_markers() {
    local file="$1"
    [ -f "$file" ] || return 0
    local state
    state="$(awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
        $0 == b { nb++; if (ne > 0) bad = 1 }
        $0 == e { ne++; if (nb == 0) bad = 1 }
        END { print (nb == 0 && ne == 0) || (!bad && nb == 1 && ne == 1) ? "ok" : "bad" }
    ' "$file")"
    if [ "$state" != ok ]; then
        echo "error: $file has an inconsistent omarchy-clean block (markers '$BEGIN_MARK' / '$END_MARK')." >&2
        echo "Fix or remove the block manually, then re-run. The file was not modified." >&2
        exit 1
    fi
}

install_system() {
    local missing=()
    for pkg in "${PACKAGES[@]}"; do
        pacman -Q "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done
    if [ "${#missing[@]}" -gt 0 ]; then
        echo "Missing packages. Install them first with:" >&2
        echo "  sudo pacman -S ${missing[*]}" >&2
        exit 1
    fi

    sudo install -d -m 755 "$LIB_DIR" "$LIB_DIR/src" "$LIB_DIR/src/omarchy_clean" "$LIB_DIR/bin"
    sudo install -m 644 "$SRC_DIR"/src/omarchy_clean/*.py "$LIB_DIR/src/omarchy_clean/"
    sudo install -m 755 "$SRC_DIR/bin/omarchy-clean" "$SRC_DIR/bin/omarchy-clean-helper" "$LIB_DIR/bin/"

    sudo install -d -m 755 "$PREFIX/bin"
    sudo ln -sf "$LIB_DIR/bin/omarchy-clean" "$PREFIX/bin/omarchy-clean"

    sudo install -d -m 755 "$POLICY_DIR"
    local policy
    policy="$(mktemp)"
    sed "s|@HELPER_PATH@|$LIB_DIR/bin/omarchy-clean-helper|" \
        "$SRC_DIR/packaging/dev.omarchy.clean.policy.in" > "$policy"
    sudo install -m 644 "$policy" "$POLICY_DIR/dev.omarchy.clean.policy"
    rm -f "$policy"
}

enable_polkit_agent() {
    if systemctl --user cat hyprpolkitagent.service >/dev/null 2>&1; then
        systemctl --user enable --now hyprpolkitagent.service || echo "warning: could not enable hyprpolkitagent" >&2
    else
        echo "warning: hyprpolkitagent.service not found; skipping (install hyprpolkitagent)" >&2
    fi
}

add_keybind() {
    local file="$HYPR_CONFIG_DIR/bindings.lua"
    mkdir -p "$HYPR_CONFIG_DIR"
    touch "$file"
    if grep -qF -- "$BEGIN_MARK" "$file"; then
        return
    fi
    # Keep the original bytes intact: only add a newline if the file lacks one.
    if [ -s "$file" ] && [ -n "$(tail -c1 "$file")" ]; then
        echo >> "$file"
    fi
    {
        echo "$BEGIN_MARK"
        echo 'o.bind("SUPER + SHIFT + K", "Clean keyboard", "omarchy-clean 60")'
        echo "$END_MARK"
    } >> "$file"
}

write_desktop_file() {
    mkdir -p "$APPS_DIR"
    cat > "$APPS_DIR/omarchy-clean.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Clean Keyboard
Comment=Lock keyboard and trackpad for cleaning
Exec=omarchy-clean 60
Icon=input-keyboard
Categories=Utility;
DESKTOP
}

[ "$keybind" -eq 0 ] || validate_markers "$HYPR_CONFIG_DIR/bindings.lua"
[ "$user_only" -eq 1 ] || install_system
enable_polkit_agent
[ "$keybind" -eq 0 ] || add_keybind
write_desktop_file
if command -v hyprctl >/dev/null 2>&1; then
    hyprctl reload >/dev/null 2>&1 || true
fi
echo "omarchy-clean installed."
