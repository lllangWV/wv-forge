@echo on

mkdir build
cd build

cmake %CMAKE_ARGS% ^
    -GNinja ^
    -DCMAKE_BUILD_TYPE=Release ^
    -DCMAKE_INSTALL_PREFIX="%LIBRARY_PREFIX%" ^
    -DCMAKE_PREFIX_PATH="%LIBRARY_PREFIX%" ^
    -DOPTION_BUILD_CCVIEWER=ON ^
    -DOPTION_USE_SHAPE_LIB=ON ^
    -DOPTION_USE_DXF_LIB=ON ^
    -DOPTION_MP_BUILD=ON ^
    ^
    -DPLUGIN_GL_QEDL=ON ^
    -DPLUGIN_GL_QSSAO=ON ^
    -DPLUGIN_IO_QCORE=ON ^
    ^
    -DPLUGIN_IO_QLAS=ON ^
    -DLASZIP_INCLUDE_DIR="%LIBRARY_PREFIX%\include" ^
    -DLASZIP_LIBRARY="%LIBRARY_PREFIX%\lib\laszip.lib" ^
    ^
    -DPLUGIN_IO_QE57=ON ^
    -DXercesC_INCLUDE_DIR="%LIBRARY_PREFIX%\include" ^
    -DXercesC_LIBRARY="%LIBRARY_PREFIX%\lib\xerces-c_3.lib" ^
    -DE57Format_DIR="%LIBRARY_PREFIX%\lib\cmake\E57Format" ^
    ^
    -DPLUGIN_STANDARD_QANIMATION=ON ^
    -DQANIMATION_WITH_FFMPEG_SUPPORT=ON ^
    -DFFMPEG_INCLUDE_DIR="%LIBRARY_PREFIX%\include" ^
    -DFFMPEG_LIBRARY_DIR="%LIBRARY_PREFIX%\lib" ^
    ^
    -DCCCORELIB_USE_CGAL=ON ^
    -DCGAL_DIR="%LIBRARY_PREFIX%\lib\cmake\CGAL" ^
    ^
    -DPLUGIN_IO_QDRACO=ON ^
    -Ddraco_DIR="%LIBRARY_PREFIX%\lib\cmake\draco" ^
    ^
    -DPLUGIN_STANDARD_QRANSAC_SD=ON ^
    ^
    -DPLUGIN_STANDARD_QPOISSON_RECON=ON ^
    ..
if errorlevel 1 exit 1

ninja -j%CPU_COUNT%
if errorlevel 1 exit 1

ninja install
if errorlevel 1 exit 1
