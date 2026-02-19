#!/bin/bash
set -ex

mkdir -p build
cd build

cmake ${CMAKE_ARGS} \
    -GNinja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_PREFIX_PATH="${PREFIX}" \
    -DE57_BUILD_TEST=OFF \
    -DE57_BUILD_SHARED=ON \
    ..

ninja -j${CPU_COUNT}
ninja install
