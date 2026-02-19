# Building Pointcept from Source with Custom CUDA/PyTorch Versions

This directory contains rattler-build recipes for building Pointcept and its
dependencies entirely from source, allowing you to choose any CUDA and PyTorch
version combination.

## Dependency Chain

```
ccimport (available on conda-forge)
    ↓
pccm (Python C++ Code Manager)
    ↓
cumm (CUDA Matrix Multiply library)
    ↓
spconv (Spatial Sparse Convolution)
    ↓
pointcept (Point Cloud Perception Framework)
    └── pointops (custom CUDA extension)
```

## Directory Structure

```
ext_pkgs/
├── pixi.toml           # Main workspace with build tasks
├── README.md           # This file
├── pccm/
│   ├── pixi.toml
│   └── recipe/
│       └── recipe.yaml
├── cumm/
│   ├── pixi.toml
│   └── recipe/
│       ├── recipe.yaml
│       └── variants.yaml
├── spconv/
│   ├── pixi.toml
│   └── recipe/
│       ├── recipe.yaml
│       └── variants.yaml
└── pointcept/
    ├── pixi.toml
    └── recipe/
        ├── recipe.yaml
        └── variants.yaml
```

## Quick Start

### 1. Build All Packages

```bash
# Build entire dependency chain with default CUDA 12.4
pixi run build-all

# Or build with specific CUDA version
pixi run -e cuda118 build-all
pixi run -e cuda124 build-all
pixi run -e cuda126 build-all
```

### 2. Build Individual Packages

```bash
pixi run build-pccm      # Pure Python, no CUDA
pixi run build-cumm      # CUDA extension
pixi run build-spconv    # CUDA extension
pixi run build-pointcept # CUDA extension + Python package
```

## Creating Patches

When building from source, you may need to patch the original packages to work
with conda's build system. Here's the workflow:

### Step 1: Setup Debug Environment

```bash
# This downloads source and sets up build environment without running build
pixi run debug-cumm
```

### Step 2: Make Modifications

Navigate to the work directory and make your changes:

```bash
cd cumm/output/bld/rattler-build_cumm_*/work
# Edit files as needed, e.g., fix hardcoded paths
```

### Step 3: Generate Patch

```bash
pixi run create-patch-cumm
```

This creates `cumm/recipe/conda-fixes.patch` containing your changes.

### Step 4: Add Patch to Recipe

Edit `cumm/recipe/recipe.yaml`:

```yaml
source:
  git: https://github.com/FindDefinition/cumm.git
  tag: v0.7.11
  patches:
    - conda-fixes.patch
```

### Step 5: Rebuild

```bash
pixi run build-cumm
```

## Common Patches Needed

### cumm - CUDA Path Detection

cumm may have hardcoded CUDA paths. Create a patch to use `$CUDA_HOME`:

```diff
--- a/setup.py
+++ b/setup.py
@@ -50,7 +50,8 @@ def get_cuda_version():
-    cuda_home = "/usr/local/cuda"
+    cuda_home = os.environ.get("CUDA_HOME", os.environ.get("CONDA_PREFIX", "/usr/local/cuda"))
```

### spconv - Boost Detection

spconv may need help finding Boost in conda environment:

```diff
--- a/setup.py
+++ b/setup.py
@@ -30,6 +30,9 @@ import os
+# Use conda's Boost
+os.environ.setdefault("BOOST_ROOT", os.environ.get("CONDA_PREFIX", ""))
```

### pointcept - pointops Build

pointops may need CUDA_HOME set correctly:

```diff
--- a/libs/pointops/setup.py
+++ b/libs/pointops/setup.py
@@ -1,5 +1,10 @@
 import os
+# Ensure CUDA_HOME is set for conda builds
+if "CONDA_PREFIX" in os.environ and "CUDA_HOME" not in os.environ:
+    os.environ["CUDA_HOME"] = os.environ["CONDA_PREFIX"]
```

## Supported CUDA Versions

| CUDA Version | GPU Architectures |
|--------------|-------------------|
| 11.8 | 60, 70, 75, 80, 86, 89, 90 |
| 12.4 | 60, 70, 75, 80, 86, 89, 90 |
| 12.6 | 60, 70, 75, 80, 86, 89, 90 |

## Supported PyTorch Versions

- PyTorch 2.1.x - 2.5.x
- Must match CUDA version (e.g., PyTorch built with CUDA 12.4)

## Troubleshooting

### CUDA not found

Ensure `cuda-toolkit` is in host requirements and `CUDA_HOME` is set:

```yaml
requirements:
  host:
    - cuda-toolkit
```

### GCC version mismatch

CUDA has GCC version requirements:
- CUDA 11.x: GCC ≤ 11
- CUDA 12.x: GCC ≤ 12

Use `c_stdlib_version` in variants if needed.

### Missing CUDA libraries

For CUDA 12+, explicitly add development packages:

```yaml
requirements:
  host:
    - cuda-cudart-dev
    - libcublas-dev
    - libcurand-dev
```

### Build takes too long

Reduce GPU architectures in `CUMM_CUDA_ARCH_LIST`:

```bash
# Build only for your specific GPU (e.g., RTX 3090 = 8.6)
export CUMM_CUDA_ARCH_LIST="8.6"
```

## Using Built Packages

After building, packages are in `{package}/output/` directories. To use them:

```bash
# Create a new environment with local channel
pixi init my-project
cd my-project

# Add local channel to pixi.toml
# channels = ["file:///path/to/ext_pkgs/pointcept/output", "conda-forge", "nvidia"]

pixi add pointcept
```

## Contributing Patches

If you create patches that fix common issues, please consider:

1. Upstream the fix to the original repository
2. Share the patch in this repository for others

## References

- [rattler-build documentation](https://rattler-build.prefix.dev/)
- [pixi-build documentation](https://pixi.sh/latest/build/)
- [spconv repository](https://github.com/traveller59/spconv)
- [cumm repository](https://github.com/FindDefinition/cumm)
- [Pointcept repository](https://github.com/Pointcept/Pointcept)
