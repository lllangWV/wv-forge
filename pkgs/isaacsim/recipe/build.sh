#!/bin/bash
set -euxo pipefail

# ============================================================================
# Isaac Sim build script for conda packaging
#   
# This script runs the NVIDIA proprietary build system (premake5 + packman)
# which downloads the Omniverse Kit SDK and other dependencies during build.
# Internet access is required.
# ============================================================================

# --- Accept EULA for automated builds ---
touch "${SRC_DIR}/.eula_accepted"

# --- Configure environment ---
export OMNI_REPO_ROOT="${SRC_DIR}"
export CUDA_HOME="${BUILD_PREFIX}"

# The Docker build container's $HOME/.cache is not writable.
# Redirect all XDG cache paths (used by packman, repo_man, etc.) into the build tree.
export XDG_CACHE_HOME="${SRC_DIR}/_cache"
mkdir -p "${XDG_CACHE_HOME}"

# Redirect NVIDIA packman cache explicitly (checked before XDG fallback).
export PM_PACKAGES_ROOT="${XDG_CACHE_HOME}/packman"
mkdir -p "${PM_PACKAGES_ROOT}"

# Packman's bundled Python 3.10 binary links against libcrypt.so.1, which was
# removed in Alma Linux 9+ (replaced by libcrypt.so.2 from libxcrypt).
# Create a compat symlink so packman's Python can load.
# The public API is the same between SONAME 1 and 2.
COMPAT_LIB_DIR="${SRC_DIR}/_compat_libs"
mkdir -p "${COMPAT_LIB_DIR}"
LIBCRYPT_REAL=$(find /lib64 /usr/lib64 /lib /usr/lib -name 'libcrypt.so.2*' -not -name '*.hmac' -not -path '*/fipscheck/*' -type f 2>/dev/null | head -1)
if [ -n "${LIBCRYPT_REAL}" ] && [ ! -f "${COMPAT_LIB_DIR}/libcrypt.so.1" ]; then
    ln -sf "${LIBCRYPT_REAL}" "${COMPAT_LIB_DIR}/libcrypt.so.1"
    echo "Created libcrypt.so.1 compat symlink -> ${LIBCRYPT_REAL}"
fi
# Also add conda's libstdc++ to the library path. The Kit SDK binary (from
# packman) requires GLIBCXX_3.4.30 which the system libstdc++ may lack.
# Conda's GCC toolchain provides a sufficiently new version.
export LD_LIBRARY_PATH="${COMPAT_LIB_DIR}:${BUILD_PREFIX}/lib:${PREFIX}/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# The conda build environment sets PIP_NO_INDEX=1 (and possibly PIP_NO_DEPS) to
# prevent pip from downloading packages during normal conda builds. Isaac Sim's
# build system uses its own bundled Python + pip with --isolated (which ignores
# PIP_* env vars for the parent process). However, pip's build isolation
# subprocess (for building sdists like pyperclip) does NOT use --isolated and
# WILL be affected by these env vars. Unset them so the build isolation
# subprocess can download setuptools from PyPI.
unset PIP_NO_INDEX 2>/dev/null || true
unset PIP_NO_DEPS 2>/dev/null || true
unset PIP_NO_BUILD_ISOLATION 2>/dev/null || true
unset PIP_REQUIRE_VIRTUALENV 2>/dev/null || true

# --- Build Isaac Sim using the project's own build system ---
# The build system (repo.sh -> packman -> premake5 -> make) handles:
# 1. Downloading Omniverse Kit SDK, PhysX, USD, and other NVIDIA components
# 2. Generating build files with premake5
# 3. Compiling C++ extensions with CUDA support
# 4. Staging all files into _build/<platform>/<config>/

# Determine the platform directory name
ARCH=$(uname -m)
BUILD_PLATFORM="linux-${ARCH}"
BUILD_DIR="${SRC_DIR}/_build/${BUILD_PLATFORM}/release"

# Disable the GCC version assertion in repo.toml — the build system's
# version detection doesn't work correctly in the conda build environment.
sed -i 's/enable_compiler_version_check = true/enable_compiler_version_check = false/' "${SRC_DIR}/repo.toml"

# Verify the C++ compiler version. Isaac Sim REQUIRES GCC 11 — the Kit SDK
# headers have implicit pointer conversions that are errors in GCC 14, and nvcc
# cannot parse GCC 14's C++ standard library headers. The recipe's variants.yaml
# pins c_compiler_version/cxx_compiler_version to 11 so conda provides GCC 11.
echo "Using C++ compiler: $(${CXX:-g++} --version | head -1)"

# Fix library name: the v5.1.0 premake5 scripts reference the Windows DLL name
# "isaacsim.util.debug_draw.primitive_drawing" in global (unfiltered) links.
# On Linux the library is "isaacsim.util.debug_draw.plugin". Replace all occurrences.
for lua_file in \
    "${SRC_DIR}/source/extensions/isaacsim.asset.gen.omap/premake5.lua" \
    "${SRC_DIR}/source/extensions/isaacsim.sensors.physx/premake5.lua"; do
    if [ -f "${lua_file}" ]; then
        sed -i 's/isaacsim\.util\.debug_draw\.primitive_drawing/isaacsim.util.debug_draw.plugin/g' "${lua_file}"
    fi
done

chmod +x "${SRC_DIR}/repo.sh"
"${SRC_DIR}/repo.sh" build -r || {
    echo "ERROR: Isaac Sim build failed"
    echo "Check that internet access is available for packman dependency downloads"
    exit 1
}

# --- Install built artifacts ---
INSTALL_DIR="${PREFIX}/share/isaacsim"
mkdir -p "${INSTALL_DIR}"
mkdir -p "${PREFIX}/bin"

# Verify build output exists
if [ ! -d "${BUILD_DIR}" ]; then
    echo "ERROR: Build output not found at ${BUILD_DIR}"
    echo "Available directories in _build/:"
    ls -la "${SRC_DIR}/_build/" 2>/dev/null || echo "  (none)"
    exit 1
fi

# Copy core directories. Use -aL to dereference symlinks — the build output
# contains symlinks to packman cache and source dirs that won't exist at runtime.
for dir in kit exts extsDeprecated extscache apps python_packages tools; do
    if [ -d "${BUILD_DIR}/${dir}" ]; then
        echo "Copying ${dir}..."
        cp -aL "${BUILD_DIR}/${dir}" "${INSTALL_DIR}/"
    fi
done

# Copy standalone examples
if [ -d "${BUILD_DIR}/standalone_examples" ]; then
    echo "Copying standalone_examples..."
    cp -aL "${BUILD_DIR}/standalone_examples" "${INSTALL_DIR}/"
fi

# Copy VERSION file
if [ -f "${SRC_DIR}/VERSION" ]; then
    cp "${SRC_DIR}/VERSION" "${INSTALL_DIR}/"
fi

# Copy launch scripts
for script in isaac-sim.sh python.sh setup_ros_env.sh; do
    if [ -f "${BUILD_DIR}/${script}" ]; then
        cp "${BUILD_DIR}/${script}" "${INSTALL_DIR}/"
        chmod +x "${INSTALL_DIR}/${script}"
    fi
done

# --- Create wrapper scripts in $PREFIX/bin ---

# Main launcher
cat > "${PREFIX}/bin/isaac-sim" << 'WRAPPER'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISAACSIM_DIR="$(cd "${SCRIPT_DIR}/../share/isaacsim" && pwd)"
export RESOURCE_NAME="IsaacSim"
exec "${ISAACSIM_DIR}/isaac-sim.sh" "$@"
WRAPPER
chmod +x "${PREFIX}/bin/isaac-sim"

# Python wrapper (uses Isaac Sim's bundled Python 3.11 with Kit kernel)
cat > "${PREFIX}/bin/isaac-sim-python" << 'WRAPPER'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISAACSIM_DIR="$(cd "${SCRIPT_DIR}/../share/isaacsim" && pwd)"
if [ -f "${ISAACSIM_DIR}/python.sh" ]; then
    exec "${ISAACSIM_DIR}/python.sh" "$@"
else
    echo "Error: Isaac Sim Python wrapper not found at ${ISAACSIM_DIR}/python.sh"
    exit 1
fi
WRAPPER
chmod +x "${PREFIX}/bin/isaac-sim-python"

echo "Isaac Sim installed to ${INSTALL_DIR}"
echo "Launch with: isaac-sim"
echo "Python with: isaac-sim-python"
