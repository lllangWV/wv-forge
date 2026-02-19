# Variant Build System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor all wv-forge package recipes to use rattler-build variants for CUDA (12.6, 12.8, 12.9) and Python (3.12, 3.13), following conda-forge conventions, and create a build script that builds and uploads everything to the wv-forge prefix.dev channel.

**Architecture:** A shared `variants.yaml` at the repo root defines the build matrix. Each recipe uses unpinned `python` and `cuda-version` in `host:` so the variant system injects versions at build time. CUDA packages use the "enhanced compatibility" pattern (ignore run_exports from -dev packages, manually pin with `pin_compatible`). A `build_all.sh` script orchestrates dependency-ordered builds and uploads.

**Tech Stack:** rattler-build (variants, build, upload), conda-forge conventions (recipe.yaml v1 format), prefix.dev (wv-forge channel)

---

### Task 1: Create variants.yaml

**Files:**
- Create: `variants.yaml`

**Step 1: Write the variant configuration file**

Create `variants.yaml` at the repo root with the Python and CUDA version matrix:

```yaml
# variants.yaml — build matrix for wv-forge packages
# rattler-build reads this file via -m flag to expand recipes into multiple builds.

python:
  - "3.12"
  - "3.13"

cuda_version:
  - "12.6"
  - "12.8"
  - "12.9"
```

**Step 2: Verify rattler-build can render with it**

Run: `rattler-build build --render-only -r pkgs/pccm/recipe/recipe.yaml -m variants.yaml --ignore-recipe-variants -c conda-forge 2>&1 | head -40`

Expected: Recipe renders successfully (noarch package, variant keys not consumed).

**Step 3: Commit**

```bash
git add variants.yaml
git commit -m "Add variants.yaml for CUDA and Python build matrix"
```

---

### Task 2: Refactor pccm recipe (noarch, no CUDA)

**Files:**
- Modify: `pkgs/pccm/recipe/recipe.yaml`

**Step 1: Update the recipe**

The recipe is already noarch and well-structured. Add `extra.recipe-maintainers` for conda-forge readiness. Use `${{ PYTHON }}` in script for consistency. Keep all deps as-is since pccm has no globally-pinned deps that need unpinning.

Replace the full file with:

```yaml
# Recipe for pccm - Python C++ Code Manager
# https://github.com/FindDefinition/PCCM

context:
  version: "0.4.16"

package:
  name: pccm
  version: ${{ version }}

source:
  git: https://github.com/FindDefinition/PCCM.git
  tag: v${{ version }}

build:
  number: 0
  noarch: python
  script: ${{ PYTHON }} -m pip install . -vv --no-deps --no-build-isolation

requirements:
  host:
    - python >=3.9
    - pip
    - setuptools >=41.0
    - wheel
  run:
    - python >=3.9
    - ccimport >=0.3.1
    - pybind11 >=2.6.0
    - fire
    - lark >=1.0.0
    - portalocker >=2.3.2

tests:
  - python:
      imports:
        - pccm
      pip_check: true

about:
  homepage: https://github.com/FindDefinition/PCCM
  license: MIT
  license_file: LICENSE
  summary: Python C++ Code Manager - A tool for generating and building C++ code from Python

extra:
  recipe-maintainers:
    - lllangWV
```

**Step 2: Verify render**

Run: `rattler-build build --render-only -r pkgs/pccm/recipe/recipe.yaml --ignore-recipe-variants -c conda-forge 2>&1 | head -20`

Expected: Single noarch build rendered, no variant expansion.

**Step 3: Commit**

```bash
git add pkgs/pccm/recipe/recipe.yaml
git commit -m "Update pccm recipe for conda-forge compatibility"
```

---

### Task 3: Refactor pipeline recipe (noarch, no CUDA)

**Files:**
- Modify: `pkgs/pipeline/recipe/recipe.yaml`

**Step 1: Update the recipe**

Add `extra.recipe-maintainers`. Use `${{ PYTHON }}` for consistency.

Replace the full file with:

```yaml
# Recipe for pipeline - Multithreaded Python data pipeline framework
# https://github.com/EasternJournalist/pipeline

context:
  version: "1.0.0"
  commit: "866f059d2a05cde05e4a52211ec5051fd5f276d6"

package:
  name: pipeline
  version: ${{ version }}

source:
  url: https://github.com/EasternJournalist/pipeline/archive/${{ commit }}.tar.gz
  sha256: 36e2fc484c98ff4b9e007457ab45b71009434e9834992336bd2efda22f532523

build:
  number: 0
  noarch: python
  script:
    content: |
      ${{ PYTHON }} -m pip install . -vv --no-deps --no-build-isolation

requirements:
  host:
    - python >=3.8
    - pip
    - setuptools >=61.0
    - wheel
  run:
    - python >=3.8

tests:
  - python:
      imports:
        - pipeline

about:
  homepage: https://github.com/EasternJournalist/pipeline
  license: MIT
  license_file: LICENSE
  summary: A multithreaded Python framework for building concurrent data pipelines
  repository: https://github.com/EasternJournalist/pipeline

extra:
  recipe-maintainers:
    - lllangWV
```

**Step 2: Verify render**

Run: `rattler-build build --render-only -r pkgs/pipeline/recipe/recipe.yaml --ignore-recipe-variants -c conda-forge 2>&1 | head -20`

Expected: Single noarch build rendered.

**Step 3: Commit**

```bash
git add pkgs/pipeline/recipe/recipe.yaml
git commit -m "Update pipeline recipe for conda-forge compatibility"
```

---

### Task 4: Refactor cumm recipe (CUDA variant-driven)

**Files:**
- Modify: `pkgs/cumm/recipe/recipe.yaml`

**Step 1: Update the recipe to use variant keys**

Key changes:
- `python` bare in `host:` (variant injects version)
- `cuda-version` bare in `host:` (variant injects version)
- `build.variant.use_keys: [cuda_version]` forces CUDA into hash
- `CUMM_CUDA_VERSION` derived from variant via `${{ cuda_version }}`
- `run:` uses `pin_compatible` for python and cuda-version
- Add `extra.recipe-maintainers`

Replace the full file with:

```yaml
# Recipe for cumm - CUDA Matrix Multiply library
# https://github.com/FindDefinition/cumm

context:
  version: "0.7.11"

package:
  name: cumm
  version: ${{ version }}

source:
  git: https://github.com/FindDefinition/cumm.git
  tag: v${{ version }}
  patches:
    - patches/conda-cuda-paths.patch

build:
  number: 0
  skip:
    - not linux
  variant:
    use_keys:
      - cuda_version
  script:
    env:
      CUMM_DISABLE_JIT: "1"
      CUMM_CUDA_VERSION: "${{ cuda_version }}"
      CUMM_CUDA_ARCH_LIST: "7.0;7.5;8.0;8.6;8.9;9.0"
    content: |
      export CUDA_HOME=$PREFIX
      $PYTHON -m pip install . -vv --no-deps --no-build-isolation

requirements:
  build:
    - ${{ compiler('c') }}
    - ${{ compiler('cxx') }}
    - cmake
    - ninja
  host:
    - python
    - pip
    - setuptools >=41.0
    - wheel
    - pccm >=0.4.15
    - ccimport >=0.4.4
    - pybind11 >=2.6.0
    - numpy
    - sympy
    - fire
    - cuda-version
    - cuda-cudart-dev
    - cuda-nvcc
    - libcublas-dev
    - libcurand-dev
    - cuda-nvrtc-dev
    - cuda-profiler-api
    - libcusparse-dev
  run:
    - ${{ pin_compatible('python', upper_bound='x.x') }}
    - pccm >=0.4.15
    - ccimport >=0.4.4
    - pybind11 >=2.6.0
    - numpy
    - sympy
    - fire
    - ${{ pin_compatible('cuda-version', lower_bound='x.x', upper_bound='x') }}
    - cuda-cudart
    - ${{ pin_compatible('cuda-nvrtc', lower_bound='x.x', upper_bound='x.x') }}
    - libcublas
    - libcurand
    - libcusparse
  ignore_run_exports:
    from_package:
      - cuda-cudart-dev
      - libcublas-dev
      - libcurand-dev
      - cuda-nvrtc-dev
      - libcusparse-dev
    by_name:
      - cuda-version

tests:
  - python:
      imports:
        - cumm
      pip_check: true

about:
  homepage: https://github.com/FindDefinition/cumm
  license: Apache-2.0
  license_file: LICENSE
  summary: CUDA Matrix Multiply library with Python bindings

extra:
  recipe-maintainers:
    - lllangWV
```

**Step 2: Verify variant expansion**

Run: `rattler-build build --render-only -r pkgs/cumm/recipe/recipe.yaml -m variants.yaml -c conda-forge -c nvidia 2>&1 | grep -E "python|cuda_version|variant"`

Expected: 6 variants rendered (2 Python x 3 CUDA).

**Step 3: Commit**

```bash
git add pkgs/cumm/recipe/recipe.yaml
git commit -m "Refactor cumm recipe to use variant-driven CUDA and Python"
```

---

### Task 5: Refactor spconv recipe (CUDA variant-driven)

**Files:**
- Modify: `pkgs/spconv/recipe/recipe.yaml`

**Step 1: Update the recipe to use variant keys**

Same pattern as cumm. Key additions: spconv also needs `libboost-devel` and depends on `cumm`.

Replace the full file with:

```yaml
# Recipe for spconv - Spatial Sparse Convolution Library
# https://github.com/traveller59/spconv

context:
  version: "2.3.6"

package:
  name: spconv
  version: ${{ version }}

source:
  git: https://github.com/traveller59/spconv.git
  tag: v${{ version }}
  patches:
    - patches/conda-cuda-boost-paths.patch

build:
  number: 0
  skip:
    - not linux
  variant:
    use_keys:
      - cuda_version
  script:
    env:
      SPCONV_DISABLE_JIT: "1"
      CUMM_CUDA_VERSION: "${{ cuda_version }}"
      CUMM_CUDA_ARCH_LIST: "7.0;7.5;8.0;8.6;8.9;9.0"
    content: |
      export CUDA_HOME=$PREFIX
      export BOOST_ROOT=$PREFIX/include
      $PYTHON -m pip install . -vv --no-deps --no-build-isolation

requirements:
  build:
    - ${{ compiler('c') }}
    - ${{ compiler('cxx') }}
    - cmake
    - ninja
  host:
    - python
    - pip
    - setuptools >=41.0
    - wheel
    - pccm >=0.4.16
    - ccimport >=0.4.4
    - pybind11 >=2.6.0
    - numpy
    - fire
    - cumm >=0.7.11,<0.8.0
    - cuda-version
    - cuda-cudart-dev
    - cuda-nvcc
    - libcublas-dev
    - libcurand-dev
    - cuda-nvrtc-dev
    - cuda-profiler-api
    - libcusparse-dev
    - libboost-devel >=1.77.0
  run:
    - ${{ pin_compatible('python', upper_bound='x.x') }}
    - pccm >=0.4.16
    - ccimport >=0.4.4
    - numpy
    - fire
    - cumm >=0.7.11,<0.8.0
    - ${{ pin_compatible('cuda-version', lower_bound='x.x', upper_bound='x') }}
    - cuda-cudart
    - ${{ pin_compatible('cuda-nvrtc', lower_bound='x.x', upper_bound='x.x') }}
    - libcublas
    - libcurand
    - libcusparse
  ignore_run_exports:
    from_package:
      - cuda-cudart-dev
      - libcublas-dev
      - libcurand-dev
      - cuda-nvrtc-dev
      - libcusparse-dev
    by_name:
      - cuda-version

tests:
  - python:
      imports:
        - spconv
      pip_check: false

about:
  homepage: https://github.com/traveller59/spconv
  license: Apache-2.0
  license_file: LICENSE
  summary: Spatial Sparse Convolution Library for 3D point cloud processing

extra:
  recipe-maintainers:
    - lllangWV
```

**Step 2: Verify variant expansion**

Run: `rattler-build build --render-only -r pkgs/spconv/recipe/recipe.yaml -m variants.yaml -c conda-forge -c nvidia -c https://prefix.dev/wv-forge 2>&1 | grep -E "python|cuda_version|variant"`

Expected: 6 variants rendered.

**Step 3: Commit**

```bash
git add pkgs/spconv/recipe/recipe.yaml
git commit -m "Refactor spconv recipe to use variant-driven CUDA and Python"
```

---

### Task 6: Refactor pointcept recipe (CUDA variant-driven)

**Files:**
- Modify: `pkgs/pointcept/recipe/recipe.yaml`

**Step 1: Update the recipe to use variant keys**

Key changes: unpinned `python` and `cuda-version`, variant-driven. Keep `pytorch-gpu >=2.6.0` as that's the minimum the upstream project requires.

Replace the full file with:

```yaml
# Recipe for Pointcept - Point Cloud Perception Framework
# https://github.com/Pointcept/Pointcept

context:
  version: "1.6.0"

package:
  name: pointcept
  version: ${{ version }}

source:
  git: https://github.com/Pointcept/Pointcept.git
  tag: v${{ version }}
  patches:
    - patches/conda-pointops-cuda.patch

build:
  number: 0
  skip:
    - not linux
  variant:
    use_keys:
      - cuda_version
  script:
    env:
      TORCH_CUDA_ARCH_LIST: "7.0;7.5;8.0;8.6;8.9;9.0"
    content: |
      export CUDA_HOME=$PREFIX

      # Copy the pointcept module to site-packages
      mkdir -p $PREFIX/lib/python$PY_VER/site-packages/pointcept
      cp -r pointcept/* $PREFIX/lib/python$PY_VER/site-packages/pointcept/

      # Build and install pointops extension
      cd libs/pointops
      $PYTHON setup.py build_ext --inplace
      $PYTHON setup.py install --single-version-externally-managed --record=record.txt
      cd ../..

      # Copy configs and tools for convenience
      mkdir -p $PREFIX/share/pointcept
      cp -r configs $PREFIX/share/pointcept/
      cp -r tools $PREFIX/share/pointcept/

requirements:
  build:
    - ${{ compiler('c') }}
    - ${{ compiler('cxx') }}
    - cmake
    - ninja
  host:
    - python
    - pip
    - setuptools >=41.0
    - wheel
    - pytorch-gpu >=2.6.0
    - numpy
    - cuda-version
    - cuda-cudart-dev
    - cuda-nvcc
    - libcusparse-dev
    - libcublas-dev
    - libcusolver-dev
  run:
    - ${{ pin_compatible('python', upper_bound='x.x') }}
    - pytorch-gpu >=2.6.0
    - torchvision
    - ${{ pin_compatible('cuda-version', lower_bound='x.x', upper_bound='x') }}
    - cuda-cudart
    - spconv
    - numpy
    - scipy
    - h5py
    - plyfile
    - pyyaml
    - addict
    - yapf
    - termcolor
    - timm
    - einops
    - sharedarray
    - tensorboard
    - tensorboardx
  ignore_run_exports:
    from_package:
      - cuda-cudart-dev
      - libcusparse-dev
      - libcublas-dev
      - libcusolver-dev
    by_name:
      - cuda-version

tests:
  - python:
      imports:
        - pointcept
      pip_check: false

about:
  homepage: https://github.com/Pointcept/Pointcept
  license: MIT
  license_file: LICENSE
  summary: Point Cloud Perception Framework for 3D understanding

extra:
  recipe-maintainers:
    - lllangWV
```

**Step 2: Verify variant expansion**

Run: `rattler-build build --render-only -r pkgs/pointcept/recipe/recipe.yaml -m variants.yaml -c conda-forge -c nvidia -c https://prefix.dev/wv-forge 2>&1 | grep -E "python|cuda_version|variant"`

Expected: 6 variants rendered.

**Step 3: Commit**

```bash
git add pkgs/pointcept/recipe/recipe.yaml
git commit -m "Refactor pointcept recipe to use variant-driven CUDA and Python"
```

---

### Task 7: Refactor pytorch3d recipe (CUDA variant-driven)

**Files:**
- Modify: `pkgs/pytorch3d/recipe/recipe.yaml`

**Step 1: Update the recipe to use variant keys**

Key changes: remove hardcoded `python 3.12.*` → bare `python`, remove `cuda-version >=12.6` → bare `cuda-version`. Keep `pytorch-gpu >=2.8.0,<2.10.0` as the upstream-tested range.

Replace the full file with:

```yaml
# Recipe for PyTorch3D - 3D deep learning library from Meta FAIR
# https://github.com/facebookresearch/pytorch3d

context:
  version: "0.7.9"

package:
  name: pytorch3d
  version: ${{ version }}

source:
  url: https://github.com/facebookresearch/pytorch3d/archive/v${{ version }}.tar.gz
  sha256: 96c1ef357c522e1f45b5f9c27bae9b75185034457ddbcacdd343a0ec50bc515f

build:
  number: 0
  skip:
    - not linux
  variant:
    use_keys:
      - cuda_version
  script:
    env:
      FORCE_CUDA: "1"
      TORCH_CUDA_ARCH_LIST: "7.0;7.5;8.0;8.6;8.9;9.0+PTX"
      MAX_JOBS: "${CPU_COUNT}"
    content: |
      $PYTHON -m pip install . -vv --no-build-isolation

requirements:
  build:
    - ${{ compiler('c') }}
    - ${{ compiler('cxx') }}
  host:
    - python
    - pip
    - setuptools
    - ninja
    - numpy
    - pytorch-gpu >=2.8.0,<2.10.0
    - cuda-version
    - cuda-nvcc
    - cuda-cccl
    - cuda-cudart-dev
    - libcusparse-dev
    - libcusolver-dev
    - libcublas-dev
  run:
    - ${{ pin_compatible('python', upper_bound='x.x') }}
    - pytorch-gpu >=2.8.0,<2.10.0
    - ${{ pin_compatible('cuda-version', lower_bound='x.x', upper_bound='x') }}
    - cuda-cudart
    - iopath
    - fvcore
    - numpy
  ignore_run_exports:
    from_package:
      - cuda-cudart-dev
      - libcusparse-dev
      - libcusolver-dev
      - libcublas-dev
    by_name:
      - cuda-version

tests:
  - python:
      imports:
        - pytorch3d
        - pytorch3d.structures
        - pytorch3d.renderer
        - pytorch3d.ops
        - pytorch3d.loss
        - pytorch3d.io

about:
  homepage: https://github.com/facebookresearch/pytorch3d
  license: BSD-3-Clause
  license_file: LICENSE
  summary: PyTorch3D is FAIR's library of reusable components for deep learning with 3D data
  repository: https://github.com/facebookresearch/pytorch3d
  documentation: https://pytorch3d.org/

extra:
  recipe-maintainers:
    - lllangWV
```

**Step 2: Verify variant expansion**

Run: `rattler-build build --render-only -r pkgs/pytorch3d/recipe/recipe.yaml -m variants.yaml -c conda-forge -c nvidia 2>&1 | grep -E "python|cuda_version|variant"`

Expected: 6 variants rendered.

**Step 3: Commit**

```bash
git add pkgs/pytorch3d/recipe/recipe.yaml
git commit -m "Refactor pytorch3d recipe to use variant-driven CUDA and Python"
```

---

### Task 8: Refactor moge recipe (noarch, no CUDA)

**Files:**
- Modify: `pkgs/moge/recipe/recipe.yaml`

**Step 1: Update the recipe**

moge is pure Python (noarch). Add `extra.recipe-maintainers`. Use `${{ PYTHON }}`.

Replace the full file with:

```yaml
# Recipe for MoGe - Monocular Geometry Estimation
# https://github.com/microsoft/MoGe

context:
  version: "2.0.0"
  commit: "07444410f1e33f402353b99d6ccd26bd31e469e8"

package:
  name: moge
  version: ${{ version }}

source:
  url: https://github.com/microsoft/MoGe/archive/${{ commit }}.tar.gz
  sha256: 08e5fcbaa4421a0e3e284ac7e3196965904677bb479c29b19c95ead47407f734

build:
  number: 0
  noarch: python
  script:
    content: |
      ${{ PYTHON }} -m pip install . -vv --no-deps --no-build-isolation

requirements:
  host:
    - python >=3.9
    - pip
    - setuptools >=61.0
    - wheel
  run:
    - python >=3.9
    - click
    - opencv
    - scipy
    - matplotlib
    - trimesh
    - pillow
    - huggingface_hub
    - numpy
    - pytorch-gpu >=2.0.0
    - torchvision
    - gradio
    - utils3d
    - pipeline

tests:
  - python:
      imports:
        - moge

about:
  homepage: https://github.com/microsoft/MoGe
  license: MIT
  license_file: LICENSE
  summary: "MoGe: Unlocking Accurate Monocular Geometry Estimation for Open-Domain Images"
  repository: https://github.com/microsoft/MoGe

extra:
  recipe-maintainers:
    - lllangWV
```

**Step 2: Verify render**

Run: `rattler-build build --render-only -r pkgs/moge/recipe/recipe.yaml --ignore-recipe-variants -c conda-forge 2>&1 | head -20`

Expected: Single noarch build rendered.

**Step 3: Commit**

```bash
git add pkgs/moge/recipe/recipe.yaml
git commit -m "Update moge recipe for conda-forge compatibility"
```

---

### Task 9: Refactor sam3d-objects recipe (CUDA variant-driven)

**Files:**
- Modify: `pkgs/sam3d-objects/recipe/recipe.yaml`

**Step 1: Update the recipe to use variant keys**

Key changes: remove hardcoded `python 3.12.*` → bare `python`, add `variant.use_keys`, add `ignore_run_exports` pattern. Note: sam3d-objects is a pure Python package but has CUDA deps at runtime, so it needs variant hashing for the Python version. Since it depends on pytorch3d/spconv which are variant-built, the solver will match CUDA versions through those deps.

Actually, sam3d-objects doesn't compile any CUDA code itself — it's a pure Python package that depends on CUDA packages at runtime. The question is whether it needs CUDA variant keys. Since it doesn't link anything, it only needs Python variants. However, keeping `cuda_version` in `use_keys` would create unnecessarily many builds. Let's make it `noarch: python` if possible — but it has a linux-only `skip` and depends on architecture-specific packages like pytorch3d. For conda-forge, a noarch Python package CAN depend on arch-specific packages. The solver handles this. So let's make it noarch.

Replace the full file with:

```yaml
# Recipe for SAM 3D Objects - 3D object generation from Meta FAIR
# https://github.com/facebookresearch/sam-3d-objects

context:
  version: "0.0.1"

package:
  name: sam3d-objects
  version: ${{ version }}

source:
  path: ..

build:
  number: 0
  noarch: python
  script:
    content: |
      ${{ PYTHON }} -m pip install . -vv --no-deps --no-build-isolation

requirements:
  host:
    - python >=3.12
    - pip
    - hatchling
    - hatch-requirements-txt
  run:
    - python >=3.12
    # Core
    - pytorch-gpu >=2.8.0,<2.10.0
    - torchvision
    - numpy
    - pillow
    - tqdm
    - loguru
    - scipy
    # Config / training
    - omegaconf
    - hydra-core
    - lightning
    - safetensors
    - optree
    - timm
    # 3D / geometry
    - pytorch3d
    - gsplat
    - open3d
    - trimesh
    - kaolin
    - plyfile
    - pyvista
    - pymeshfix
    - python-igraph
    # Visualization
    - matplotlib
    - plotly
    - seaborn
    - imageio
    - opencv
    # Attention backends
    - flash-attn
    # Mono depth / misc 3D
    - utils3d
    - xatlas-python
    - moge
    - pipeline
    # Misc
    - astor
    - easydict
    - huggingface_hub

tests:
  - script:
      - LIDRA_SKIP_INIT=1 ${{ PYTHON }} -c "import sam3d_objects"

about:
  homepage: https://github.com/facebookresearch/sam-3d-objects
  license: Apache-2.0
  license_file: LICENSE
  summary: SAM 3D Objects - 3D object generation from Meta FAIR
  repository: https://github.com/facebookresearch/sam-3d-objects

extra:
  recipe-maintainers:
    - lllangWV
```

**Step 2: Verify render**

Run: `rattler-build build --render-only -r pkgs/sam3d-objects/recipe/recipe.yaml --ignore-recipe-variants -c conda-forge 2>&1 | head -20`

Expected: Single noarch build rendered.

**Step 3: Commit**

```bash
git add pkgs/sam3d-objects/recipe/recipe.yaml
git commit -m "Refactor sam3d-objects recipe to noarch with conda-forge compatibility"
```

---

### Task 10: Create build_all.sh build and upload script

**Files:**
- Create: `build_all.sh`

**Step 1: Write the build script**

```bash
#!/usr/bin/env bash
# build_all.sh — Build and upload all wv-forge packages to prefix.dev
#
# Usage:
#   ./build_all.sh              # Build all packages
#   ./build_all.sh cumm spconv  # Build specific packages
#
# Environment:
#   PREFIX_API_KEY  — prefix.dev API key (or use `rattler-build auth login prefix.dev`)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
VARIANT_CONFIG="$REPO_ROOT/variants.yaml"
OUTPUT_DIR="$REPO_ROOT/output"
CHANNEL="wv-forge"
PREFIX_URL="https://prefix.dev"

# Channels for dependency resolution (order matters: local channel first)
CHANNELS=(
  "-c" "$PREFIX_URL/$CHANNEL"
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

# Upload all .conda files from the output directory
upload_packages() {
  local pkg_count=0
  for pkg in $(find "$OUTPUT_DIR" -name "*.conda" -newer "$REPO_ROOT/.build_marker" 2>/dev/null); do
    log_info "Uploading: $(basename "$pkg")"
    rattler-build upload prefix -c "$CHANNEL" "$pkg" --skip-existing
    pkg_count=$((pkg_count + 1))
  done
  if [ "$pkg_count" -eq 0 ]; then
    log_warn "No new packages to upload"
  else
    log_info "Uploaded $pkg_count package(s)"
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

  if [ $? -eq 0 ]; then
    log_info "Built $name successfully"
  else
    log_error "Failed to build $name"
    return 1
  fi
}

# Build a CUDA/Python variant package
build_variants() {
  local name="$1"
  local recipe_dir="$2"

  log_info "Building variant package: $name (Python x CUDA matrix)"
  rattler-build build \
    -r "$recipe_dir" \
    -m "$VARIANT_CONFIG" \
    "${CHANNELS[@]}" \
    --output-dir "$OUTPUT_DIR" \
    --skip-existing local

  if [ $? -eq 0 ]; then
    log_info "Built $name variants successfully"
  else
    log_error "Failed to build $name"
    return 1
  fi
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
log_info "Upload channel: $PREFIX_URL/$CHANNEL"
if [ ${#BUILD_ONLY[@]} -gt 0 ]; then
  log_info "Building only: ${BUILD_ONLY[*]}"
fi
echo ""

# ────────────────────────────────────────────
# Level 0: Noarch base packages (no CUDA deps)
# ────────────────────────────────────────────
build_level "0 - Base (noarch)" \
  "noarch:pccm:$REPO_ROOT/pkgs/pccm/recipe" \
  "noarch:pipeline:$REPO_ROOT/pkgs/pipeline/recipe"

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
# Level 3: pointcept + pytorch3d (independent, CUDA variants)
# ────────────────────────────────────────────
build_level "3 - pointcept + pytorch3d" \
  "variant:pointcept:$REPO_ROOT/pkgs/pointcept/recipe" \
  "variant:pytorch3d:$REPO_ROOT/pkgs/pytorch3d/recipe"

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
log_info "Packages available at: $PREFIX_URL/$CHANNEL"
```

**Step 2: Make it executable**

Run: `chmod +x build_all.sh`

**Step 3: Test dry run (render only)**

Verify the script structure is correct by running a quick test:

Run: `rattler-build build --render-only -r pkgs/cumm/recipe -m variants.yaml -c conda-forge -c nvidia 2>&1 | head -40`

Expected: Renders 6 variant combinations.

**Step 4: Commit**

```bash
git add build_all.sh
git commit -m "Add build_all.sh for variant builds and prefix.dev upload"
```

---

### Task 11: Test a full dry-run render of all recipes

**Files:**
- None (verification only)

**Step 1: Render all variant recipes**

Run these commands to verify all recipes render correctly:

```bash
# Noarch packages
rattler-build build --render-only -r pkgs/pccm/recipe --ignore-recipe-variants -c conda-forge 2>&1 | tail -5
rattler-build build --render-only -r pkgs/pipeline/recipe --ignore-recipe-variants -c conda-forge 2>&1 | tail -5

# Variant packages
rattler-build build --render-only -r pkgs/cumm/recipe -m variants.yaml -c conda-forge -c nvidia 2>&1 | tail -10
rattler-build build --render-only -r pkgs/spconv/recipe -m variants.yaml -c conda-forge -c nvidia -c https://prefix.dev/wv-forge 2>&1 | tail -10
rattler-build build --render-only -r pkgs/pointcept/recipe -m variants.yaml -c conda-forge -c nvidia -c https://prefix.dev/wv-forge 2>&1 | tail -10
rattler-build build --render-only -r pkgs/pytorch3d/recipe -m variants.yaml -c conda-forge -c nvidia 2>&1 | tail -10

# Noarch with runtime CUDA deps
rattler-build build --render-only -r pkgs/moge/recipe --ignore-recipe-variants -c conda-forge 2>&1 | tail -5
rattler-build build --render-only -r pkgs/sam3d-objects/recipe --ignore-recipe-variants -c conda-forge -c https://prefix.dev/wv-forge 2>&1 | tail -5
```

Expected: All recipes render without errors. Variant packages show 6 variants each.

**Step 2: Fix any render errors**

If any recipe fails to render, fix the YAML syntax or dependency issues.

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "Fix recipe render issues from dry-run verification"
```

---

### Task 12: Final integration commit

**Files:**
- None (just a clean-up commit if needed)

**Step 1: Review all changes**

Run: `git diff HEAD~11 --stat` to see all changes across the implementation.

**Step 2: Verify the repository is clean**

Run: `git status`

Expected: No uncommitted changes except build artifacts in `output/` or `.pixi/`.

**Step 3: Update .gitignore if needed**

Ensure `output/` is in `.gitignore` so build artifacts aren't committed:

```bash
echo "output/" >> .gitignore
git add .gitignore
git commit -m "Add output/ to .gitignore"
```
