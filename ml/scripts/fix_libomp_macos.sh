#!/usr/bin/env bash
# Fix missing libomp.dylib on macOS WITHOUT Homebrew, for LightGBM AND XGBoost.
#
# Both ship a native library that links to @rpath/libomp.dylib (the OpenMP runtime),
# which isn't bundled. On a Mac without Homebrew we reuse a libomp.dylib that already
# exists (e.g. from Anaconda) by copying it next to each package's library and adding a
# @loader_path rpath so it resolves.
#
# Idempotent: safe to re-run. Run after creating the venv / (re)installing these:
#   bash ml/scripts/fix_libomp_macos.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ML_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PY="${VENV_PY:-$ML_DIR/.venv/bin/python}"

if [ ! -x "$VENV_PY" ]; then
  echo "ERROR: venv python not found at $VENV_PY (set VENV_PY=/path/to/python)"; exit 1
fi

# Find an existing libomp.dylib once (prefer Anaconda).
SRC_OMP="$(/usr/bin/find "$HOME/anaconda3" "$HOME/miniconda3" /usr/local /opt -name 'libomp.dylib' 2>/dev/null | head -n1 || true)"

# fix_pkg <module> <dylib-filename>
fix_pkg() {
  local module="$1" dylib="$2"

  # Already imports fine? Nothing to do.
  if "$VENV_PY" -c "import $module" 2>/dev/null; then
    echo "✅ $module already imports fine — skipping."
    return 0
  fi

  # locate the package's lib/ dir from its install path (works even if import fails,
  # since we only need the file location, not a working import)
  local libdir
  libdir="$("$VENV_PY" -c "import importlib.util,os; s=importlib.util.find_spec('$module'); print(os.path.join(os.path.dirname(s.origin),'lib'))" 2>/dev/null || true)"
  if [ -z "$libdir" ] || [ ! -d "$libdir" ]; then
    echo "⚠️  $module: lib dir not found (is it installed?) — skipping."
    return 0
  fi

  if [ -z "$SRC_OMP" ]; then
    echo "ERROR: no libomp.dylib found on disk. Install one (conda: "
    echo "       'conda install -c conda-forge llvm-openmp', or 'brew install libomp') then re-run."
    exit 1
  fi

  echo "$module: copying libomp from $SRC_OMP -> $libdir"
  cp "$SRC_OMP" "$libdir/libomp.dylib"

  local target="$libdir/$dylib"
  if [ -f "$target" ] && ! otool -l "$target" | grep -q "@loader_path"; then
    install_name_tool -add_rpath @loader_path "$target"
    echo "$module: added @loader_path rpath."
  fi

  if "$VENV_PY" -c "import $module; print('   $module', $module.__version__, 'OK')"; then
    echo "✅ $module fixed."
  else
    echo "❌ $module still failing — check: otool -l $target | grep -A2 LC_RPATH"; exit 1
  fi
}

fix_pkg lightgbm lib_lightgbm.dylib
fix_pkg xgboost  libxgboost.dylib

echo "done."
