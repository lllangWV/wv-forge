# CloudCompare Conda Package

This directory contains a rattler-build recipe for building CloudCompare 2.13.2 as a conda package.

## Prerequisites

- [rattler-build](https://github.com/prefix-dev/rattler-build) installed
- Internet connection (for downloading dependencies from conda-forge)

Install rattler-build via pixi:
```bash
pixi global install rattler-build
```

## Building the Package

### 1. Build libE57Format (Optional Dependency)

If you want to experiment with E57 support (currently disabled due to submodule conflicts):

```bash
cd /path/to/RattlerPackages
rattler-build build -r src/libe57format/recipe.yaml -c conda-forge
```

### 2. Build CloudCompare

```bash
cd /path/to/RattlerPackages
rattler-build build -r src/cloudcompare/recipe.yaml -c conda-forge
```

The build takes approximately 3 minutes and produces:
```
output/linux-64/cloudcompare-2.13.2-hb0f4dca_0.conda
```

## Installing the Package

### Option 1: Using pixi

Add the local channel and install:

```bash
# Create a new environment
pixi init my-cloudcompare-env
cd my-cloudcompare-env

# Add the local channel and package
pixi add --channel file:///path/to/RattlerPackages/output cloudcompare
```

### Option 2: Using conda/mamba

```bash
# Create environment with local channel
conda create -n cloudcompare -c file:///path/to/RattlerPackages/output -c conda-forge cloudcompare

# Activate
conda activate cloudcompare
```

### Option 3: Using pixi global

```bash
pixi global install cloudcompare
```

## Running CloudCompare

After installation, two executables are available:

### CloudCompare (Main Application)

```bash
CloudCompare
```

Or with a file:
```bash
CloudCompare /path/to/pointcloud.las
```

### ccViewer (Lightweight Viewer)

```bash
ccViewer
```

Or with a file:
```bash
ccViewer /path/to/pointcloud.las
```

### Command Line Options

```bash
# Open multiple files
CloudCompare file1.las file2.ply file3.bin

# Silent mode (no GUI, for batch processing)
CloudCompare -SILENT -O input.las -C_EXPORT_FMT LAS -SAVE_CLOUDS

# Get help
CloudCompare --help
```

## Included Plugins

| Plugin | Description | Status |
|--------|-------------|--------|
| QLAS IO | LAS/LAZ point cloud files | Enabled |
| QDRACO IO | Google Draco compressed files | Enabled |
| QCORE IO | Basic file formats (PLY, OBJ, etc.) | Enabled |
| QRANSAC SD | RANSAC shape detection | Enabled |
| QPOISSON RECON | Poisson surface reconstruction | Enabled |
| QANIMATION | Animation creation | Enabled (no video export) |
| QEDL | Eye-Dome Lighting shader | Enabled |
| QSSAO | Screen-Space Ambient Occlusion | Enabled |
| CGAL | Computational geometry algorithms | Enabled |

## Excluded Plugins

| Plugin | Reason |
|--------|--------|
| E57 IO | Bundled submodule conflicts with system library |
| PCL | Complex dependency conflicts with other packages |
| PDAL | Dependency conflicts |
| FBX IO | Requires proprietary Autodesk SDK |
| FFmpeg encoding | API incompatibility with FFmpeg 6.0+ |

## Supported File Formats

**Read/Write:**
- LAS/LAZ (LiDAR)
- PLY (Stanford)
- OBJ (Wavefront)
- STL (Stereolithography)
- OFF (Object File Format)
- DXF (AutoCAD)
- SHP (Shapefile)
- Draco (Google compressed)
- ASCII/CSV point clouds
- BIN (CloudCompare native)

## Troubleshooting

### Display Issues

If you encounter OpenGL errors:
```bash
# Try software rendering
export LIBGL_ALWAYS_SOFTWARE=1
CloudCompare
```

### Missing Libraries

If libraries are not found, ensure the conda environment is activated:
```bash
conda activate cloudcompare
# or
pixi shell
```

### Permission Denied

Ensure the executables have execute permission:
```bash
chmod +x $CONDA_PREFIX/bin/CloudCompare
chmod +x $CONDA_PREFIX/bin/ccViewer
```

## Build Configuration

The package is built with:
- Qt 5.15
- CGAL (header-only)
- Boost 1.84
- LASzip
- Draco
- GMP/MPFR

See `BUILD_COMPLICATIONS.md` for detailed notes on build issues encountered.

## License

CloudCompare is licensed under GPL-2.0-or-later. See the `license.txt` file in the source repository.
