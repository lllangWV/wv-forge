"""Quick smoke test for sam3d-objects package."""

import os

os.environ["LIDRA_SKIP_INIT"] = "1"

import sam3d_objects

print(f"sam3d_objects imported successfully")

# Verify key submodules are importable
from sam3d_objects import config, data, model, pipeline, utils

print("All submodules imported successfully")

# Check that core dependencies are available
import torch
import numpy as np

print(f"PyTorch version: {torch.__version__}")
print(f"NumPy version: {np.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")

print("\nsam3d-objects smoke test passed!")
