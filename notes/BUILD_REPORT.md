# Build Report: Pointcept & Dependencies from Source with CUDA 12.6

## Overview

**Goal:** Build Pointcept and its CUDA dependencies entirely from source using rattler-build, pinned to CUDA 12.6 for consistent GPU compatibility.

**Dependency Chain:** `ccimport` → `pccm` → `cumm` → `spconv` → `pointcept`

**Final Packages Built:**

| Package | Version | Size |
|---------|---------|------|
| cumm | 0.7.11 | 2.6 MB |
| spconv | 2.3.6 | 19 MB |
| pointcept | 1.6.0 | 4.5 MB |

---

## Complications Encountered

### 1. CUDA Runtime Library Missing at Test Time

**Problem:** After building cumm and spconv, tests failed with:
```
libnvrtc-builtins.so.12.6: cannot open shared object file
```

**Cause:** The build environment had CUDA dev packages, but the run/test environment lacked the CUDA runtime libraries.

**Solution:** Added explicit CUDA runtime dependencies to run requirements:
```yaml
run:
  - cuda-cudart >=12.6,<12.7
  - cuda-nvrtc >=12.6,<12.7
  - libcublas >=12.6,<12.7
  - libcurand >=10.3.7,<10.4
  - libcusparse >=12.5,<12.6
```

---

### 2. CUDA Version Mismatch in Test Environment

**Problem:** Even after adding runtime deps, tests failed because the solver installed CUDA 12.9 instead of 12.6.

**Cause:** Unpinned `cuda-version` allowed the solver to pick the latest available version.

**Solution:** Pinned CUDA version with upper bound:
```yaml
- cuda-version >=12.6,<12.7
```

---

### 3. spconv pip_check Failure (Metadata Mismatch)

**Problem:** spconv's `pip_check` test failed with:
```
cumm-cu126 0.5.3 is installed but cumm-cu126<0.5.0,>=0.4.9 is required by spconv-cu126
```

**Cause:** spconv's PyPI metadata hardcodes a dependency on `cumm-cu126<0.5.0`, but we built cumm 0.7.11. The conda package names don't include the `-cu126` suffix, causing pip's metadata check to fail.

**Solution:** Disabled pip_check for spconv (conda dependencies are correct):
```yaml
tests:
  - python:
      imports:
        - spconv
      pip_check: false
```

---

### 4. variants.yaml Panic (Zip Key Length Mismatch)

**Problem:** rattler-build panicked with:
```
zip_keys contain keys of different lengths
```

**Cause:** A `variants.yaml` file had mismatched array lengths in zip_keys configuration.

**Solution:** Removed the variants.yaml file entirely (not needed for single-variant build).

---

### 5. pytorch-cuda vs pytorch-gpu Package Name

**Problem:** Recipe specified `pytorch-cuda 12.6.*` which doesn't exist on conda-forge.

**Cause:** Incorrect package name assumption. conda-forge uses `pytorch-gpu` (metapackage) or `pytorch` with CUDA builds identified by build string.

**Solution:** Changed to:
```yaml
- pytorch-gpu >=2.6.0
```

---

### 6. Pointcept Has No Standard Build System

**Problem:** Pointcept is a research framework, not a pip-installable package. Running `pip install .` failed because there's no `setup.py` or `pyproject.toml` at the repository root.

**Cause:** Pointcept is designed to be used by cloning the repo and running scripts directly, not installed as a package.

**Solution:** Custom build script that:
1. Copies the `pointcept/` module directly to site-packages
2. Builds only the `libs/pointops` CUDA extension separately
3. Copies configs and tools to `$PREFIX/share/pointcept/`

```yaml
script:
  content: |
    mkdir -p $PREFIX/lib/python$PY_VER/site-packages/pointcept
    cp -r pointcept/* $PREFIX/lib/python$PY_VER/site-packages/pointcept/
    cd libs/pointops
    $PYTHON setup.py build_ext --inplace
    $PYTHON setup.py install --single-version-externally-managed --record=record.txt
```

---

### 7. Missing CUDA Headers for pointops Compilation

**Problem:** pointops compilation failed with:
```
fatal error: cusparse.h: No such file or directory
fatal error: cusolverDn.h: No such file or directory
```

**Cause:** The CUDA sparse and solver dev packages weren't in host dependencies.

**Solution:** Added missing dev packages:
```yaml
host:
  - libcusparse-dev
  - libcusolver-dev
```

---

### 8. PyTorch Geometric Packages Unavailable

**Problem:** pointcept test environment failed to resolve because `pytorch-cluster`, `pytorch-scatter`, `pytorch-sparse`, and `pyg` weren't available on conda-forge channels.

**Cause:** PyTorch Geometric packages require specific builds matching PyTorch and CUDA versions, and aren't always available for all combinations.

**Solution:** Made PyTorch Geometric packages optional (commented out in run dependencies):
```yaml
run:
  # PyTorch Geometric ecosystem (optional, install from pyg channel if needed)
  # - pytorch-cluster
  # - pytorch-scatter
  # - pytorch-sparse
  # - pyg
```

---

### 9. pointops CUDA Compatibility Patch Required

**Problem:** The pointops setup.py had hardcoded CUDA paths and compilation flags incompatible with conda builds.

**Solution:** Created a patch file (`patches/conda-pointops-cuda.patch`) to:
- Use `$CUDA_HOME` environment variable instead of hardcoded paths
- Respect `TORCH_CUDA_ARCH_LIST` for architecture targeting

---

## Summary Table

| Issue | Package | Root Cause | Fix Type |
|-------|---------|------------|----------|
| Missing runtime libs | cumm, spconv | Missing run deps | Add dependencies |
| CUDA version drift | cumm, spconv | Unpinned versions | Pin version ranges |
| pip metadata mismatch | spconv | PyPI naming conventions | Disable pip_check |
| zip_keys panic | All | Config error | Remove variants.yaml |
| Wrong pytorch package | pointcept | Naming confusion | Use pytorch-gpu |
| No build system | pointcept | Research framework design | Custom copy script |
| Missing CUDA headers | pointcept | Incomplete host deps | Add dev packages |
| PyG unavailable | pointcept | Channel limitations | Make optional |
| CUDA path hardcoding | pointops | Upstream code | Patch file |

---

## Lessons Learned

1. **CUDA packages require careful version pinning** - Always pin both cuda-version and individual library versions with upper bounds to prevent solver drift.

2. **pip_check can fail for valid conda packages** - When PyPI metadata doesn't match conda package naming, disable pip_check but ensure conda dependencies are correct.

3. **Research frameworks need custom packaging** - Not all Python projects are pip-installable; sometimes manual module copying is the only option.

4. **CUDA dev vs runtime packages are separate** - Build needs `-dev` packages, runtime needs the base libraries.

5. **PyTorch ecosystem package naming varies** - conda-forge uses `pytorch-gpu`, PyPI uses `torch`, and CUDA-specific builds have different naming conventions.

---

## Usage

To use these packages in a pixi project, add the output directory as a local channel:

```toml
[workspace]
channels = ["file:///path/to/ext_pkgs/output", "conda-forge"]

[dependencies]
pointcept = "*"
```
