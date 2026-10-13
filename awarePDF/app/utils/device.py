# ============================================================
# app/utils/device.py
# Shared device detection for PyTorch model loading
# ============================================================

import torch


def get_best_device() -> str:
    """Pick the best available device for inference (CUDA > MPS > CPU)."""
    if torch.cuda.is_available():
        return "cuda"
    try:
        if torch.backends.mps.is_available():
            return "mps"
    except AttributeError:
        pass
    return "cpu"
