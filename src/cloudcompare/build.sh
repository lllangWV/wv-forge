#!/bin/bash
set -ex

mkdir -p build
cd build

cmake ${CMAKE_ARGS} \
    -GNinja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_PREFIX_PATH="${PREFIX}" \
    -DOPTION_BUILD_CCVIEWER=ON \
    -DOPTION_USE_SHAPE_LIB=ON \
    -DOPTION_USE_DXF_LIB=ON \
    \
    -DPLUGIN_GL_QEDL=ON \
    -DPLUGIN_GL_QSSAO=ON \
    -DPLUGIN_IO_QCORE=ON \
    \
    -DPLUGIN_IO_QLAS=ON \
    -DLASZIP_INCLUDE_DIR="${PREFIX}/include" \
    -DLASZIP_LIBRARY="${PREFIX}/lib/liblaszip${SHLIB_EXT}" \
    \
    -DPLUGIN_IO_QE57=ON \
    -DXercesC_INCLUDE_DIR="${PREFIX}/include" \
    -DXercesC_LIBRARY="${PREFIX}/lib/libxerces-c${SHLIB_EXT}" \
    -DE57Format_DIR="${PREFIX}/lib/cmake/E57Format" \
    \
    -DPLUGIN_STANDARD_QANIMATION=ON \
    -DQANIMATION_WITH_FFMPEG_SUPPORT=ON \
    -DFFMPEG_INCLUDE_DIR="${PREFIX}/include" \
    -DFFMPEG_LIBRARY_DIR="${PREFIX}/lib" \
    \
    -DCCCORELIB_USE_CGAL=ON \
    -DCGAL_DIR="${PREFIX}/lib/cmake/CGAL" \
    \
    -DPLUGIN_IO_QDRACO=ON \
    -Ddraco_DIR="${PREFIX}/lib/cmake/draco" \
    \
    -DPLUGIN_STANDARD_QRANSAC_SD=ON \
    \
    -DPLUGIN_STANDARD_QPOISSON_RECON=ON \
    ..

ninja -j${CPU_COUNT}
ninja install
