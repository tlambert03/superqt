#!/usr/bin/env bash
# Render the gallery's sliders with this checkout, and compare them with a baseline
# made the same way, in .gallery-baseline/ (with the latest Qt 6, Qt 6.10.0, which
# draws handles differently, and Qt 5). Windows appear while it runs.
#
#   .github/regress_local.sh baseline   # (re)make the baseline
#   .github/regress_local.sh            # compare with it
set -euo pipefail
cd "$(dirname "$0")/.."

run() {  # <name> <QT_API> <uv run options...>
    local name=$1 api=$2
    shift 2
    local out=.gallery-baseline/$name
    if [[ ${MODE:-} != baseline ]]; then
        out=$(mktemp -d)/$name
    fi
    rm -rf "$out"
    for pages in styles napari; do
        QT_API=$api uv run -q --no-project --isolated "$@" --with-editable . \
            python .github/slider_gallery.py render after "$out" "$pages" >/dev/null
    done
    if [[ ${MODE:-} != baseline ]]; then
        echo "== $name"
        QT_API=$api uv run -q --no-project --isolated "$@" --with-editable . \
            python .github/slider_gallery.py regress ".gallery-baseline/$name" "$out" \
            || status=1
    fi
}

MODE=${1:-}
status=0
run qt6 pyqt6 --with pyqt6
run qt6.10.0 pyqt6 --with pyqt6-qt6==6.10.0 --with "pyqt6>=6.10,<6.11"
run qt5 pyqt5 --with pyqt5
exit $status
