#!/usr/bin/env bash
# build_all.sh — Build and upload all wv-forge packages
#
# Usage:
#   ./build_all.sh              # Build all packages
#   ./build_all.sh cumm spconv  # Build specific packages
#
# Environment (set in .env or export):
#   WV_FORGE_CHANNEL_URL  — Channel URL for dependency resolution
#                           (default: s3://wv-forge)
#   S3_ACCESS_KEY_ID      — S3 access key for upload and channel auth
#   S3_SECRET_ACCESS_KEY  — S3 secret key for upload and channel auth
#   S3_BUCKET             — S3 bucket name (default: wv-forge)
#   S3_REGION             — S3 region (default: us-east-1)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
VARIANT_CONFIG="$REPO_ROOT/variants.yaml"
OUTPUT_DIR="$REPO_ROOT/output"

# Load .env if present
if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    source "$REPO_ROOT/.env"
    set +a
fi

# Configurable channel URL (default: S3)
CHANNEL_URL="${WV_FORGE_CHANNEL_URL:-s3://wv-forge/wv-forge}"
S3_BUCKET="${S3_BUCKET:-wv-forge/wv-forge}"
S3_REGION="${S3_REGION:-us-east-2}"

# Channels for dependency resolution (order matters: our channel first)
CHANNELS=(
  "-c" "$CHANNEL_URL"
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

# ─────────────────────────────────────────────
# Set up RATTLER_AUTH_FILE for S3 channel access
# ─────────────────────────────────────────────
if [[ "$CHANNEL_URL" == s3://* ]] && [ -n "${S3_ACCESS_KEY_ID:-}" ] && [ -n "${S3_SECRET_ACCESS_KEY:-}" ]; then
    log_info "Setting up S3 authentication for channel: $CHANNEL_URL"
    AUTH_FILE="/tmp/rattler_auth_build_all.json"
    cat > "$AUTH_FILE" <<AUTHEOF
{
    "$CHANNEL_URL": {
        "S3Credentials": {
            "access_key_id": "$S3_ACCESS_KEY_ID",
            "secret_access_key": "$S3_SECRET_ACCESS_KEY",
            "session_token": null
        }
    }
}
AUTHEOF
    export RATTLER_AUTH_FILE="$AUTH_FILE"

    # Export standard AWS env vars so the SDK credential chain finds them.
    # rattler-build's S3 channel resolution uses the AWS SDK (not S3_* vars).
    export AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY_ID"
    export AWS_SECRET_ACCESS_KEY="$S3_SECRET_ACCESS_KEY"
    export AWS_DEFAULT_REGION="$S3_REGION"
    export AWS_REGION="$S3_REGION"
elif [[ "$CHANNEL_URL" == s3://* ]]; then
    log_warn "S3 channel URL detected but S3 credentials not set — builds may fail to resolve deps"
fi

# ─────────────────────────────────────────────
# Create channel_sources override for variant builds
# ─────────────────────────────────────────────
# variants.yaml has a static channel_sources. We override it with the
# configured channel URL. Later -m files override earlier ones.
CHANNEL_OVERRIDE="/tmp/channel_override.yaml"
cat > "$CHANNEL_OVERRIDE" <<CHEOF
channel_sources:
  - "$CHANNEL_URL,conda-forge,nvidia"
CHEOF

# Upload all .conda files from the output directory that are newer than the marker
upload_packages() {
  local pkg_count=0
  for pkg in $(find "$OUTPUT_DIR" -name "*.conda" -newer "$REPO_ROOT/.build_marker" 2>/dev/null); do
    log_info "Publishing: $(basename "$pkg")"
    rattler-build publish "$pkg" --to "s3://$S3_BUCKET"
    pkg_count=$((pkg_count + 1))
  done
  if [ "$pkg_count" -eq 0 ]; then
    log_warn "No new packages to upload"
  else
    log_info "Published $pkg_count package(s)"
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
  # Variant builds get channels from channel_sources in the -m files.
  # Using -c flags here would conflict with channel_sources.
  rattler-build build \
    -r "$recipe_dir" \
    -m "$VARIANT_CONFIG" \
    -m "$CHANNEL_OVERRIDE" \
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
log_info "Channel: $CHANNEL_URL"
log_info "Upload target: s3://$S3_BUCKET (region: $S3_REGION)"
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
log_info "Packages available at: s3://$S3_BUCKET"
