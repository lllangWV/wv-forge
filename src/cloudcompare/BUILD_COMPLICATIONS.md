# CloudCompare Build Complications Report

This document summarizes all complications encountered while creating a rattler-build recipe for CloudCompare 2.13.2.

## 1. Missing Package: libE57Format

**Problem:** The `libe57format` library required for E57 file support is not available on conda-forge.

**Attempted Solution:** Created a separate recipe (`src/libe57format/`) to build libE57Format 3.3.0 from source. The package built successfully.

**Final Outcome:** E57 plugin disabled because CloudCompare's qE57IO plugin uses a bundled libE57Format submodule rather than accepting a system library. The plugin's CMakeLists.txt calls `add_subdirectory()` on the bundled source, making it incompatible with pre-installed libraries.

---

## 2. Dependency Resolution Conflicts

**Problem:** Complex dependency conflicts between major libraries when trying to include PCL, PDAL, and CGAL together.

### Conflict Chain:
```
PCL >=1.12 requires:
  └─ boost-cpp (specific versions)
      └─ icu (specific versions)

CGAL requires:
  └─ boost-cpp (different versions)
      └─ icu (conflicting versions)

Qt5 requires:
  └─ icu >=75.1
  └─ libxcb (specific versions)

xerces-c requires:
  └─ icu >=78.1 (conflicts with Qt5's icu requirement)
```

**Solution:** Removed PCL and PDAL from the build. Kept CGAL, Qt5, and xerces-c which can coexist with careful version pinning.

---

## 3. Git Submodules Not Included in Source Tarball

**Problem:** The GitHub release tarball (`CloudCompare-2.13.2.tar.gz`) does not include git submodules. The build failed with:
```
The source directory libs/qCC_db/extern/CCCoreLib does not contain a CMakeLists.txt file.
```

**Solution:** Changed source from URL tarball to git clone:
```yaml
source:
  git: https://github.com/CloudCompare/CloudCompare.git
  tag: v${{ version }}
```

Added `git submodule update --init --recursive` to the build script.

---

## 4. Rattler-Build Script File Discovery

**Problem:** External build scripts (`build.sh`, `bld.bat`) were not being copied to the work directory, causing:
```
bash: build.sh: No such file or directory
```

**Solution:** Converted to inline scripts in the recipe.yaml instead of referencing external files.

---

## 5. CMake Minimum Version Compatibility

**Problem:** Some CloudCompare subprojects use `cmake_minimum_required(VERSION 3.0)` which is incompatible with CMake 4.x:
```
Compatibility with CMake < 3.5 has been removed from CMake.
```

**Solution:** Added `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` to the CMake configuration.

---

## 6. Draco Plugin Configuration

**Problem:** CloudCompare's Draco plugin requires explicit path variables that aren't auto-detected:
```
CMake Error: Draco include dir not specified (DRACO_INCLUDE_DIR)
CMake Error: Draco library dir not specified (DRACO_LIB_DIR)
```

**Solution:** Added explicit CMake variables:
```
-DDRACO_INCLUDE_DIR="${PREFIX}/include"
-DDRACO_LIB_DIR="${PREFIX}/lib"
-DDRACO_LIBRARY="${PREFIX}/lib/libdraco.so"
```

---

## 7. FFmpeg API Incompatibility

**Problem:** CloudCompare's QTFFmpegWrapper uses deprecated FFmpeg APIs that were removed in FFmpeg 6.0:
```cpp
error: 'avcodec_close' was not declared in this scope
```

The `avcodec_close()` function was deprecated in FFmpeg 5.x and removed in FFmpeg 6.0.

**Solution:** Disabled FFmpeg encoding support:
```
-DQANIMATION_WITH_FFMPEG_SUPPORT=OFF
```

The QAnimation plugin still works for creating animations, but cannot encode to video formats.

---

## 8. License File Naming

**Problem:** Recipe specified `license_file: LICENSE` but CloudCompare uses `license.txt`:
```
Error: No license files were copied
```

**Solution:** Updated to `license_file: license.txt`.

---

## 9. Rattler-Build Syntax Changes

**Problem:** Older rattler-build syntax was rejected:
```
`max_pin` is not supported anymore. Please use `upper_bound='x.x'` instead.
```

**Solution:** Updated pin syntax in libe57format recipe:
```yaml
# Old
- ${{ pin_subpackage('libe57format', max_pin='x.x') }}
# New
- ${{ pin_subpackage('libe57format', upper_bound='x.x') }}
```

---

## 10. Non-Existent Packages on conda-forge

**Problem:** Several packages referenced in initial recipe don't exist:
- `mesa-libgl-devel` - Does not exist
- `libe57format` - Does not exist

**Solution:**
- Replaced `mesa-libgl-devel` with `mesalib` and `libglu`
- Built libe57format from source (though ultimately not used)

---

## 11. FBX SDK Unavailability

**Problem:** Autodesk FBX SDK is proprietary and cannot be distributed through conda-forge.

**Solution:** FBX plugin cannot be included. Users requiring FBX support must build CloudCompare locally with the SDK.

---

## Summary of Final Build Configuration

### Enabled Features:
- Core CloudCompare + ccViewer
- LAS/LAZ support (via LASzip)
- Draco 3D compression
- CGAL geometry algorithms
- RANSAC shape detection
- Poisson surface reconstruction
- QAnimation (without video encoding)
- GL plugins (QEDL, QSSAO)
- Shape/DXF file support

### Disabled Features:
- E57 file support (bundled submodule conflict)
- PCL plugin (dependency conflicts)
- PDAL plugin (dependency conflicts)
- FBX file support (proprietary SDK)
- FFmpeg video encoding (API incompatibility)

### Build Time Issues:
- Total compilation: ~3 minutes
- 481 build targets
- Requires ~500MB disk space for build environment
