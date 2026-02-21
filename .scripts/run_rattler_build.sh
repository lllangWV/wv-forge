#!/usr/bin/env bash
# run_rattler_build.sh -- Runs inside Docker to build wv-forge packages
# with rattler-build. Invoked by build_locally.py.
#
# Environment variables (set by the Docker launcher):
#   BUILD_PACKAGES    - Semicolon-delimited "type:name:recipe_dir" specs
#   SCCACHE_ENABLED   - "1" to enable sccache, "0" to disable
#   HOST_USER_ID      - UID of the host user (for output file ownership)

set -euo pipefail

REPO="/home/conda/wv-forge"
VARIANT_CONFIG="$REPO/variants.yaml"
OUTPUT_DIR="$REPO/output"

# Channels for dependency resolution (order matters: our channel first)
CHANNELS=(
    "-c" "https://prefix.dev/wv-forge"
    "-c" "conda-forge"
    "-c" "nvidia"
)

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ─────────────────────────────────────────────
# 1. Install rattler-build and sccache
# ─────────────────────────────────────────────
log_info "Installing rattler-build and sccache..."

micromamba install --root-prefix /opt/conda --prefix /opt/conda \
    --yes --override-channels --channel conda-forge \
    rattler-build sccache

export PATH="/opt/conda/bin:$PATH"

rattler-build --version
sccache --version

# ─────────────────────────────────────────────
# 2. Configure sccache
# ─────────────────────────────────────────────
if [ "${SCCACHE_ENABLED:-1}" = "1" ]; then
    log_info "Configuring sccache..."
    export CMAKE_C_COMPILER_LAUNCHER=sccache
    export CMAKE_CXX_COMPILER_LAUNCHER=sccache
    export SCCACHE_DIR="/home/conda/.cache/sccache"
    export SCCACHE_CACHE_SIZE="20G"

    # Start sccache server
    sccache --start-server 2>/dev/null || true
    sccache --show-stats || true
else
    log_info "sccache disabled"
fi

# ─────────────────────────────────────────────
# 3. Build each package
# ─────────────────────────────────────────────
mkdir -p "$OUTPUT_DIR"

if [ -z "${BUILD_PACKAGES:-}" ]; then
    log_error "BUILD_PACKAGES is not set"
    exit 1
fi

IFS=';' read -ra PACKAGES <<< "$BUILD_PACKAGES"
TOTAL=${#PACKAGES[@]}
CURRENT=0
FAILED=()

for pkg_spec in "${PACKAGES[@]}"; do
    IFS=':' read -r build_type name recipe_path <<< "$pkg_spec"
    CURRENT=$((CURRENT + 1))

    echo ""
    log_info "════════════════════════════════════════════"
    log_info "[$CURRENT/$TOTAL] Building: $name (type: $build_type)"
    log_info "  Recipe: $recipe_path"
    log_info "════════════════════════════════════════════"

    COMMON_ARGS=(
        "--no-build-id"
        "-r" "$recipe_path"
        "${CHANNELS[@]}"
        "--output-dir" "$OUTPUT_DIR"
        "--skip-existing" "local"
    )

    BUILD_OK=true
    case "$build_type" in
        noarch)
            rattler-build build \
                "${COMMON_ARGS[@]}" \
                --ignore-recipe-variants \
                || BUILD_OK=false
            ;;
        variant)
            rattler-build build \
                "${COMMON_ARGS[@]}" \
                -m "$VARIANT_CONFIG" \
                || BUILD_OK=false
            ;;
        standard)
            rattler-build build \
                "${COMMON_ARGS[@]}" \
                || BUILD_OK=false
            ;;
        *)
            log_error "Unknown build type: $build_type"
            BUILD_OK=false
            ;;
    esac

    if [ "$BUILD_OK" = true ]; then
        log_info "Built $name successfully"
    else
        log_error "Failed to build $name"
        FAILED+=("$name")
    fi
done

# ─────────────────────────────────────────────
# 4. Fix output file ownership
# ─────────────────────────────────────────────
if [ -n "${HOST_USER_ID:-}" ] && [ "$HOST_USER_ID" != "0" ]; then
    log_info "Fixing output file ownership (uid=$HOST_USER_ID)..."
    chown -R "$HOST_USER_ID" "$OUTPUT_DIR" 2>/dev/null || true
fi

# ─────────────────────────────────────────────
# 5. Report
# ─────────────────────────────────────────────
if [ "${SCCACHE_ENABLED:-1}" = "1" ]; then
    echo ""
    log_info "sccache statistics:"
    sccache --show-stats || true
fi

echo ""
if [ ${#FAILED[@]} -gt 0 ]; then
    log_error "═══ Build completed with failures ═══"
    log_error "Failed packages: ${FAILED[*]}"
    exit 1
else
    log_info "═══ All $TOTAL package(s) built successfully ═══"
    log_info "Output: $OUTPUT_DIR"
fi
