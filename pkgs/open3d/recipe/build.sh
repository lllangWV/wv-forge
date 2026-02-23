set -euxo pipefail

export QT_HOST_PATH="$PREFIX"
export CUDA_HOME="$PREFIX"

# Patch sysroot libc.so linker script: replace absolute paths with =-prefixed
# paths so GNU ld prepends the sysroot even when invoked by nvcc (which doesn't
# pass --sysroot to the linker).
# Before: GROUP ( /lib64/libc.so.6 /usr/lib64/libc_nonshared.a ... )
# After:  GROUP ( =/lib64/libc.so.6 =/usr/lib64/libc_nonshared.a ... )
for _sysroot in "${BUILD_PREFIX}/x86_64-conda-linux-gnu/sysroot" \
                "${PREFIX}/x86_64-conda-linux-gnu/sysroot"; do
    _libc_so="${_sysroot}/usr/lib64/libc.so"
    if [ -f "${_libc_so}" ]; then
        sed -i 's| /lib64/| =/lib64/|g; s| /usr/lib64/| =/usr/lib64/|g' "${_libc_so}"
    fi
done

# Open3D's CMake uses ExternalProject_Add with GIT_REPOSITORY for Open3D-ML,
# so it expects a git repo. Initialize the extracted source as one.
pushd ${SRC_DIR}/open3d_ml
git init -b main
git add .
git -c user.email="build@local" -c user.name="build" commit -m "v${PKG_VERSION}"
git tag "v${PKG_VERSION}"
popd

mkdir -p build
cd build

# Workaround: CUDA 12+ removed nvToolsExt (replaced by header-only nvtx3),
# but PyTorch's cmake config still references CUDA::nvToolsExt target.
# Create a compatibility shim that CMake includes early via CMAKE_PROJECT_INCLUDE.
cat > nvtoolsext_compat.cmake << 'NVTX_COMPAT'
if(NOT TARGET CUDA::nvToolsExt)
  find_package(CUDAToolkit QUIET)
  add_library(CUDA::nvToolsExt INTERFACE IMPORTED)
  if(TARGET CUDA::nvtx3)
    target_link_libraries(CUDA::nvToolsExt INTERFACE CUDA::nvtx3)
  endif()
endif()
NVTX_COMPAT

cmake ${SRC_DIR} ${CMAKE_ARGS} \
    -DCMAKE_PROJECT_INCLUDE=${PWD}/nvtoolsext_compat.cmake \
    -DBUILD_CUDA_MODULE=ON \
    -DBUILD_COMMON_CUDA_ARCHS=ON \
    -DBUILD_WITH_CUDA_STATIC=OFF \
    -DBUILD_PYTORCH_OPS=ON \
    -DBUNDLE_OPEN3D_ML=ON \
    -DOPEN3D_ML_ROOT=${SRC_DIR}/open3d_ml \
    -DBUILD_TENSORFLOW_OPS=OFF \
    -DBUILD_AZURE_KINECT=OFF \
    -DBUILD_EXAMPLES=OFF \
    -DBUILD_ISPC_MODULE=OFF \
    -DBUILD_GUI=OFF \
    -DBUILD_LIBREALSENSE=OFF \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_WEBRTC=OFF \
    -DENABLE_HEADLESS_RENDERING=OFF \
    -DBUILD_JUPYTER_EXTENSION=OFF \
    -DOPEN3D_USE_ONEAPI_PACKAGES=OFF \
    -DUSE_BLAS=ON \
    -DUSE_SYSTEM_ASSIMP=ON \
    -DUSE_SYSTEM_BLAS=ON \
    -DUSE_SYSTEM_CURL=ON \
    -DUSE_SYSTEM_EIGEN3=ON \
    -DUSE_SYSTEM_EMBREE=ON \
    -DUSE_SYSTEM_FMT=ON \
    -DUSE_SYSTEM_GLEW=ON \
    -DUSE_SYSTEM_GLFW=ON \
    -DUSE_SYSTEM_GOOGLETEST=ON \
    -DUSE_SYSTEM_IMGUI=ON \
    -DUSE_SYSTEM_JPEG=ON \
    -DUSE_SYSTEM_JSONCPP=ON \
    -DUSE_SYSTEM_LIBLZF=ON \
    -DUSE_SYSTEM_LIBREALSENSE=OFF \
    -DUSE_SYSTEM_MSGPACK=ON \
    -DUSE_SYSTEM_NANOFLANN=ON \
    -DUSE_SYSTEM_OPENSSL=ON \
    -DUSE_SYSTEM_PNG=ON \
    -DUSE_SYSTEM_PYBIND11=ON \
    -DUSE_SYSTEM_QHULLCPP=ON \
    -DUSE_SYSTEM_TBB=ON \
    -DUSE_SYSTEM_TINYGLTF=OFF \
    -DUSE_SYSTEM_TINYOBJLOADER=ON \
    -DUSE_SYSTEM_VTK=ON \
    -DUSE_SYSTEM_ZEROMQ=ON \
    -DWITH_IPP=OFF \
    -DWITH_FAISS=OFF \
    -DPython3_EXECUTABLE=$PYTHON

cmake --build . --config Release -- -j$CPU_COUNT
cmake --build . --config Release --target install
cmake --build . --config Release --target install-pip-package

# De-duplicate shared libraries: install-pip-package copies the libs into
# site-packages/open3d/cuda/, duplicating the ones in $PREFIX/lib/.
# Replace the copies with relative symlinks to save ~340 MiB per package.
# Layout: $SP_DIR/open3d/cuda/libOpen3D.so.0.19 -> ../../../../libOpen3D.so.0.19
SITE_CUDA="$SP_DIR/open3d/cuda"
REL_PREFIX="$(python3 -c "import os; print(os.path.relpath('$PREFIX/lib', '$SITE_CUDA'))")"
for lib in libOpen3D.so.0.19 open3d_torch_ops.so; do
    if [ -f "$SITE_CUDA/$lib" ] && [ -e "$PREFIX/lib/$lib" ]; then
        rm "$SITE_CUDA/$lib"
        ln -s "$REL_PREFIX/$lib" "$SITE_CUDA/$lib"
    fi
done

# Create open3d/cpu/ as a mirror of open3d/cuda/ so that open3d.__init__.py
# can fall back to CPU imports when no CUDA device is available at runtime.
# A CUDA build only produces open3d/cuda/pybind*.so, but __init__.py
# unconditionally does "from open3d.cpu.pybind import ..." when it can't
# detect a GPU (e.g. in Docker test environments without drivers).
# The CUDA-built pybind .so contains all CPU symbols, so symlinking works.
SITE_CPU="$SP_DIR/open3d/cpu"
mkdir -p "$SITE_CPU"
touch "$SITE_CPU/__init__.py"
for so in "$SITE_CUDA"/pybind*.so; do
    [ -f "$so" ] || continue
    soname=$(basename "$so")
    ln -s "../cuda/$soname" "$SITE_CPU/$soname"
done
