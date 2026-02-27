#!/bin/bash
set -ex

# ShapeR has no setup.py/pyproject.toml. We create a proper Python package
# by wrapping all modules under a 'shaper' namespace and patching imports.

# Create the shaper package directory
mkdir -p shaper

# Create __init__.py
cat > shaper/__init__.py << 'EOF'
"""ShapeR - 3D Shape Reconstruction from SLAM observations."""
EOF

# Move all submodules into the shaper namespace
for dir in model dataset preprocessing postprocessing experimental; do
    if [ -d "$dir" ]; then
        cp -r "$dir" shaper/
    fi
done

# Copy the inference script
cp infer_shape.py shaper/infer_shape.py

# Patch imports in all Python files to use the shaper namespace
find shaper -name "*.py" -exec sed -i \
    -e 's/^from model\b/from shaper.model/' \
    -e 's/^from dataset\b/from shaper.dataset/' \
    -e 's/^from preprocessing\b/from shaper.preprocessing/' \
    -e 's/^from postprocessing\b/from shaper.postprocessing/' \
    -e 's/^from experimental\b/from shaper.experimental/' \
    -e 's/^import model\b/import shaper.model/' \
    -e 's/^import dataset\b/import shaper.dataset/' \
    -e 's/^import preprocessing\b/import shaper.preprocessing/' \
    -e 's/^import postprocessing\b/import shaper.postprocessing/' \
    {} +

# Create pyproject.toml
cat > pyproject.toml << 'PYPROJECT'
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "shaper"
version = "0.0.1"
requires-python = ">=3.10"

[project.scripts]
shaper-infer = "shaper.infer_shape:main"

[tool.setuptools.packages.find]
include = ["shaper*"]
PYPROJECT

$PYTHON -m pip install . -vv --no-deps --no-build-isolation
