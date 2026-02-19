# Variant Build System for wv-forge

## Goal

Build conda packages for all CUDA-dependent packages in `pkgs/` across a matrix of CUDA versions (12.6, 12.8, 12.9) and Python versions (3.12, 3.13). Recipes follow conda-forge conventions so they can be submitted upstream later. A build script handles dependency-ordered builds and uploads to the `wv-forge` prefix.dev channel.

## Variant Configuration

A single `variants.yaml` at the repo root defines the build matrix:

```yaml
python:
  - "3.12"
  - "3.13"

cuda_version:
  - "12.6"
  - "12.8"
  - "12.9"
```

This produces 6 variants (2 Python x 3 CUDA) for each CUDA package. Noarch packages build once.

## Recipe Standards (conda-forge compatible)

### Key principles

1. **No hardcoded version pins for globally-pinned packages.** `python` and `cuda-version` appear bare in `host:` — the variant system injects versions.
2. **Use `${{ compiler('c') }}`, `${{ compiler('cxx') }}`** in `build:` requirements.
3. **Use CUDA enhanced compatibility pattern:** `ignore_run_exports` from `-dev` packages + manual `pin_compatible('cuda-version', lower_bound='x.x', upper_bound='x')` in `run:`.
4. **Use `build.variant.use_keys: [cuda_version]`** to force CUDA version into the build hash.
5. **Use `pin_compatible('python', lower_bound='x.x', upper_bound='x.x')`** in `run:` to match the build-time Python.
6. **Derive environment variables from variant values** using Jinja: `CUMM_CUDA_VERSION: "${{ cuda_version }}"`.
7. **Include `extra.recipe-maintainers`** for conda-forge readiness.

### Noarch packages (no variants)

pccm, pipeline, moge — these use `noarch: python` and are built once. They skip the variant config.

### CUDA packages (variant-driven)

cumm, spconv, pointcept, pytorch3d, sam3d-objects — these consume both `python` and `cuda_version` variant keys.

## Package Build Order

```
Level 0 (noarch):    pccm, pipeline
Level 1 (variants):  cumm
Level 2 (variants):  spconv       (depends: cumm, pccm)
Level 3 (variants):  pointcept    (depends: spconv)
                     pytorch3d
Level 4 (noarch):    moge         (depends: pipeline)
Level 5 (variants):  sam3d-objects (depends: pytorch3d, moge, pipeline)
```

Each level builds and uploads before the next level starts. Within a level, independent packages can build in parallel.

## Build Script (`build_all.sh`)

Location: repo root.

### Behavior

1. Validates `PREFIX_API_KEY` is set (or uses stored auth).
2. Sets common variables: channels, output dir, variant config path.
3. For each package level:
   - Calls `rattler-build build` with `-r <recipe> -m variants.yaml -c conda-forge -c nvidia -c https://prefix.dev/wv-forge`.
   - For noarch packages, adds `--ignore-recipe-variants`.
   - Uploads all `.conda` files from output dir via `rattler-build upload prefix -c wv-forge`.
4. Logs success/failure for each package.

### Channel resolution

Packages at level 2+ need to find their level 1+ dependencies. Since we upload after each level, they are available on `https://prefix.dev/wv-forge` by the time downstream builds run.

## Recipe Changes Summary

| Package | Current State | Changes Needed |
|---------|--------------|----------------|
| pccm | noarch, good | Add `extra.recipe-maintainers`, minor cleanup |
| pipeline | noarch, good | Add `extra.recipe-maintainers` |
| cumm | Hardcoded CUDA 12.6, python >=3.10,<3.13 | Remove version pins, use variant keys, add `build.variant.use_keys` |
| spconv | Hardcoded CUDA 12.6, python >=3.10,<3.13 | Same as cumm |
| pointcept | Hardcoded CUDA 12.6, python >=3.10,<3.13 | Same as cumm, keep pytorch-gpu pin per upstream compat |
| pytorch3d | Hardcoded python 3.12, cuda >=12.6 | Use variant keys, widen python/cuda support |
| moge | noarch, good | Add `extra.recipe-maintainers` |
| sam3d-objects | Hardcoded python 3.12, local source | Use variant keys, switch to proper source URL |

## End-User Experience

After builds complete, users install via:

```toml
# pixi.toml
[workspace]
channels = ["https://prefix.dev/wv-forge", "conda-forge", "nvidia"]
platforms = ["linux-64"]

[dependencies]
python = "3.12.*"
cuda-version = "12.6.*"
pytorch-gpu = ">=2.5.0"
pointcept = "*"
spconv = "*"
```

The solver selects the matching variant automatically.
