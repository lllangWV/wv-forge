#!/usr/bin/env bash
# build_all.sh — Build and upload all wv-forge packages to prefix.dev
#
# Usage:
#   ./build_all.sh              # Build all packages
#   ./build_all.sh cumm spconv  # Build specific packages
#
# Environment:
#   PREFIX_API_KEY  — prefix.dev API key (or use `rattler-build auth login prefix.dev`)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
VARIANT_CONFIG="$REPO_ROOT/variants.yaml"
OUTPUT_DIR="$REPO_ROOT/output"
CHANNEL="wv-forge"
PREFIX_URL="https://prefix.dev"

# Channels for dependency resolution (order matters: our channel first)
CHANNELS=(
  "-c" "$PREFIX_URL/$CHANNEL"
  "-c" "conda-forge"
  "-c" "nvidia"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Upload all .conda files from the output directory that are newer than the marker
upload_packages() {
  local pkg_count=0
  for pkg in $(find "$OUTPUT_DIR" -name "*.conda" -newer "$REPO_ROOT/.build_marker" 2>/dev/null); do
    log_info "Uploading: $(basename "$pkg")"
    rattler-build upload prefix -c "$CHANNEL" "$pkg" --skip-existing
    pkg_count=$((pkg_count + 1))
  done
  if [ "$pkg_count" -eq 0 ]; then
    log_warn "No new packages to upload"
  else
    log_info "Uploaded $pkg_count package(s)"
  fi
}

# Build a noarch package (no variant expansion)
build_noarch() {
  local name="$1"
  local recipe_dir="$2"

  log_info "Building noarch package: $name"
  rattler-build build \
    -r "$recipe_dir" \
    "${CHANNELS[@]}" \
    --output-dir "$OUTPUT_DIR" \
    --skip-existing local \
    --ignore-recipe-variants

  log_info "Built $name successfully"
}

# Build a CUDA/Python variant package
build_variants() {
  local name="$1"
  local recipe_dir="$2"

  log_info "Building variant package: $name (Python x CUDA matrix)"
  rattler-build build \
    -r "$recipe_dir" \
    -m "$VARIANT_CONFIG" \
    "${CHANNELS[@]}" \
    --output-dir "$OUTPUT_DIR" \
    --skip-existing local

  log_info "Built $name variants successfully"
}

# Build a single level: build packages, then upload
build_level() {
  local level_name="$1"
  shift
  local packages=("$@")

  log_info "=== Building Level: $level_name ==="
  touch "$REPO_ROOT/.build_marker"

  for pkg_spec in "${packages[@]}"; do
    # Format: "type:name:recipe_path"
    IFS=':' read -r build_type name recipe_path <<< "$pkg_spec"

    # Skip if user specified specific packages and this isn't one
    if [ ${#BUILD_ONLY[@]} -gt 0 ]; then
      local found=false
      for target in "${BUILD_ONLY[@]}"; do
        if [ "$target" = "$name" ]; then
          found=true
          break
        fi
      done
      if [ "$found" = false ]; then
        log_info "Skipping $name (not in build list)"
        continue
      fi
    fi

    if [ "$build_type" = "noarch" ]; then
      build_noarch "$name" "$recipe_path"
    elif [ "$build_type" = "variant" ]; then
      build_variants "$name" "$recipe_path"
    fi
  done

  log_info "Uploading packages from level: $level_name"
  upload_packages
  rm -f "$REPO_ROOT/.build_marker"
}

# Parse command-line arguments
BUILD_ONLY=("${@}")

mkdir -p "$OUTPUT_DIR"

log_info "=== wv-forge Package Builder ==="
log_info "Variant config: $VARIANT_CONFIG"
log_info "Output dir: $OUTPUT_DIR"
log_info "Upload channel: $PREFIX_URL/$CHANNEL"
if [ ${#BUILD_ONLY[@]} -gt 0 ]; then
  log_info "Building only: ${BUILD_ONLY[*]}"
fi
echo ""

# ────────────────────────────────────────────
# Level 0: Noarch base packages (no CUDA deps)
# ────────────────────────────────────────────
build_level "0 - Base (noarch)" \
  "noarch:pccm:$REPO_ROOT/pkgs/pccm/recipe" \
  "noarch:pipeline:$REPO_ROOT/pkgs/pipeline/recipe" \
  "noarch:utils3d:$REPO_ROOT/pkgs/utils3d/recipe"

# ────────────────────────────────────────────
# Level 1: cumm (CUDA variants, depends on pccm)
# ────────────────────────────────────────────
build_level "1 - cumm" \
  "variant:cumm:$REPO_ROOT/pkgs/cumm/recipe"

# ────────────────────────────────────────────
# Level 2: spconv (CUDA variants, depends on cumm + pccm)
# ────────────────────────────────────────────
build_level "2 - spconv" \
  "variant:spconv:$REPO_ROOT/pkgs/spconv/recipe"

# ────────────────────────────────────────────
# Level 3: pointcept + pytorch3d + open3d (independent, CUDA variants)
# ────────────────────────────────────────────
build_level "3 - pointcept + pytorch3d + open3d" \
  "variant:pointcept:$REPO_ROOT/pkgs/pointcept/recipe" \
  "variant:pytorch3d:$REPO_ROOT/pkgs/pytorch3d/recipe" \
  "variant:open3d:$REPO_ROOT/pkgs/open3d/recipe"

# ────────────────────────────────────────────
# Level 4: moge (noarch, depends on pipeline)
# ────────────────────────────────────────────
build_level "4 - moge" \
  "noarch:moge:$REPO_ROOT/pkgs/moge/recipe"

# ────────────────────────────────────────────
# Level 5: sam3d-objects (noarch, depends on pytorch3d + moge)
# ────────────────────────────────────────────
build_level "5 - sam3d-objects" \
  "noarch:sam3d-objects:$REPO_ROOT/pkgs/sam3d-objects/recipe"

echo ""
log_info "=== All builds complete ==="
log_info "Packages available at: $PREFIX_URL/$CHANNEL"
