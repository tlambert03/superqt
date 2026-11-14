#!/usr/bin/env bash
# Render the gallery's sliders and the visual matrix with this checkout, and compare
# them, pixel by pixel, with a baseline made the same way, in .gallery-baseline/: with
# Qt 6.12.0, Qt 6.10.0 (which draws style sheets' pages with each handle) and Qt 5;
# and the next Qt, if $NEXT_PYTHON is a Python whose PyQt6 has its QtWidgets (see
# workflows/visual_matrix.yml). Windows appear while it runs: leave the computer
# alone meanwhile (whether a window is active changes how sliders look).
#
#   .github/regress_local.sh baseline   # (re)make the baseline
#   .github/regress_local.sh            # compare with it
set -euo pipefail
cd "$(dirname "$0")/.."

check() {  # <name> <QT_API> <python command...>
    local name=$1 api=$2
    shift 2
    local base=.gallery-baseline/$name out
    if [[ $MODE == baseline ]]; then
        out=$base
    else
        out=$(mktemp -d)/$name
    fi
    rm -rf "$out"
    for pages in styles napari; do
        QT_API=$api "$@" .github/slider_gallery.py render after "$out" "$pages" >/dev/null
    done
    QT_API=$api "$@" .github/visual_matrix.py render "$out/matrix" --napari >/dev/null
    if [[ $MODE != baseline ]]; then
        echo "== $name ($out)"
        QT_API=$api "$@" .github/slider_gallery.py regress "$base" "$out" 0 || status=1
        QT_API=$api "$@" .github/visual_matrix.py compare \
            "$base/matrix" "$out/matrix" "$out/matrix-changes" || status=1
    fi
}

MODE=${1:-}
status=0
UV=(uv run -q --no-project --isolated)
check qt6.12.0 pyqt6 "${UV[@]}" --with pyqt6==6.12.0 --with pyqt6-qt6==6.12.0 \
    --with-editable . python
check qt6.10.0 pyqt6 "${UV[@]}" --with pyqt6-qt6==6.10.0 --with "pyqt6>=6.10,<6.11" \
    --with-editable . python
check qt5 pyqt5 "${UV[@]}" --with pyqt5 --with-editable . python
if [[ -n ${NEXT_PYTHON:-} ]]; then
    check next pyqt6 env PYTHONPATH=src "$NEXT_PYTHON"
fi
exit $status
