#!/bin/bash
set -ex

export CUDA_HOME=$PREFIX
export TORCH_CUDA_ARCH_LIST="8.9;12.0"

# The master branch has no top-level setup.py/pyproject.toml.
# Create a proper Python package by wrapping all modules under 'learning3d'.

mkdir -p learning3d

# Copy core Python modules
for dir in data_utils losses models ops utils; do
    cp -r "$dir" learning3d/
done

# Create top-level __init__.py
cat > learning3d/__init__.py << 'EOF'
"""Learning3D: A Modern Library for Deep Learning on 3D Point Clouds Data."""
from . import models
from . import losses
from . import data_utils
from . import ops
from . import utils
EOF

# Copy pretrained models
cp -r pretrained learning3d/

# Ensure all subdirectories have __init__.py for proper package discovery
touch learning3d/utils/lib/__init__.py
touch learning3d/losses/cuda/__init__.py

# Create pyproject.toml for the main package
cat > pyproject.toml << 'PYPROJECT'
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "learning3d"
version = "0.2.2"
requires-python = ">=3.8"

[tool.setuptools.packages.find]
include = ["learning3d*"]
PYPROJECT

# ---- Build and install CUDA extensions ----

# 1. Build and install pointnet2_cuda extension (top-level module)
cd learning3d/utils/lib
# Remove stale build artifacts checked into the repo
rm -rf build dist *.egg-info __pycache__
$PYTHON setup.py install --single-version-externally-managed --record=record.txt
cd ../../..

# 2. Build and install EMD CUDA extension (top-level 'emd' and '_emd_ext' packages)
cd learning3d/losses/cuda/emd_torch
$PYTHON setup.py install --single-version-externally-managed --record=record.txt
cd ../../../..

# 3. Pre-compile chamfer distance CUDA extension
# Instead of JIT compilation at runtime, build it as a proper extension
cd learning3d/losses/cuda/chamfer_distance

cat > setup.py << 'CDSETUP'
from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension

setup(
    name='chamfer_distance_cuda',
    ext_modules=[
        CUDAExtension('cd', [
            'chamfer_distance.cpp',
            'chamfer_distance.cu',
        ]),
    ],
    cmdclass={'build_ext': BuildExtension},
)
CDSETUP

$PYTHON setup.py install --single-version-externally-managed --record=record.txt

# Patch chamfer_distance.py to use pre-compiled module instead of JIT
cat > chamfer_distance.py << 'CDPATCH'
import torch
import cd


class ChamferDistanceFunction(torch.autograd.Function):
    @staticmethod
    def forward(ctx, xyz1, xyz2):
        batchsize, n, _ = xyz1.size()
        _, m, _ = xyz2.size()
        xyz1 = xyz1.contiguous()
        xyz2 = xyz2.contiguous()
        dist1 = torch.zeros(batchsize, n)
        dist2 = torch.zeros(batchsize, m)

        idx1 = torch.zeros(batchsize, n, dtype=torch.int)
        idx2 = torch.zeros(batchsize, m, dtype=torch.int)

        if not xyz1.is_cuda:
            cd.forward(xyz1, xyz2, dist1, dist2, idx1, idx2)
        else:
            dist1 = dist1.cuda()
            dist2 = dist2.cuda()
            idx1 = idx1.cuda()
            idx2 = idx2.cuda()
            cd.forward_cuda(xyz1, xyz2, dist1, dist2, idx1, idx2)

        ctx.save_for_backward(xyz1, xyz2, idx1, idx2)

        return dist1, dist2

    @staticmethod
    def backward(ctx, graddist1, graddist2):
        xyz1, xyz2, idx1, idx2 = ctx.saved_tensors

        graddist1 = graddist1.contiguous()
        graddist2 = graddist2.contiguous()

        gradxyz1 = torch.zeros(xyz1.size())
        gradxyz2 = torch.zeros(xyz2.size())

        if not graddist1.is_cuda:
            cd.backward(
                xyz1, xyz2, gradxyz1, gradxyz2, graddist1, graddist2, idx1, idx2
            )
        else:
            gradxyz1 = gradxyz1.cuda()
            gradxyz2 = gradxyz2.cuda()
            cd.backward_cuda(
                xyz1, xyz2, gradxyz1, gradxyz2, graddist1, graddist2, idx1, idx2
            )

        return gradxyz1, gradxyz2


class ChamferDistance(torch.nn.Module):
    def forward(self, xyz1, xyz2):
        return ChamferDistanceFunction.apply(xyz1, xyz2)
CDPATCH

cd ../../../..

# ---- Install the main package ----
$PYTHON -m pip install . -vv --no-deps --no-build-isolation
