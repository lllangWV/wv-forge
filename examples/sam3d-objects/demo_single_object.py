"""Demo: Single object 3D reconstruction with SAM 3D Objects.

Converts notebook/demo_single_object.ipynb into a standalone script.
Generates a Gaussian splat from a masked image and saves a rotating GIF.

Usage:
    cd examples
    CONDA_OVERRIDE_CUDA=12.9 pixi run demo
"""

import os
import sys
import argparse
from pathlib import Path


# inference.py sets these, but set early just in case
os.environ["LIDRA_SKIP_INIT"] = "true"

import torch
from inference import (
    Inference,
    ready_gaussian_for_video_rendering,
    render_video,
    load_image,
    load_single_mask,
    make_scene,
)

# Path to the sam-3d-objects repo (images, checkpoints)
SAM3D_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "tmp", "sam-3d-objects")


def _offload_to_cpu(module):
    """Move a module (or ModuleDict) to CPU to free GPU memory."""
    if module is None:
        return
    if hasattr(module, "to"):
        module.to("cpu")
    elif hasattr(module, "model") and hasattr(module.model, "to"):
        module.model.to("cpu")


def _offload_to_gpu(module, device="cuda"):
    """Move a module back to GPU."""
    if module is None:
        return
    if hasattr(module, "parameters"):
        module.to(device)
    elif hasattr(module, "model") and hasattr(module.model, "to"):
        module.model.to(device)


class _CachedEmbedder(torch.nn.Module):
    """Dummy embedder that returns pre-computed embeddings."""
    def __init__(self, cached_tokens):
        super().__init__()
        self.cached_tokens = cached_tokens

    def forward(self, *args, **kwargs):
        return self.cached_tokens


def _gpu_mem():
    return f"{torch.cuda.memory_allocated()/1024**3:.2f} GiB"


def run_with_offloading(inference_obj, image, mask, seed=None):
    """Run inference with CPU offloading to fit in limited GPU memory.

    The depth model (MoGe) and the generation models don't need to be on GPU
    at the same time.  This function manually shuttles them between CPU and GPU.
    """
    import gc
    pipeline = inference_obj._pipeline
    device = torch.device("cuda")
    # Override pipeline device to cuda for inference (models were loaded on CPU)
    pipeline.device = device

    # Merge image + mask into RGBA (same as Inference.__call__)
    image_rgba = inference_obj.merge_mask_to_rgba(image, mask)

    # --- Stage 0: Depth estimation (MoGe) ---
    print("  [offload] Moving all models to CPU ...")
    _offload_to_cpu(pipeline.models)
    for emb in pipeline.condition_embedders.values():
        _offload_to_cpu(emb)
    gc.collect()
    torch.cuda.empty_cache()

    _offload_to_gpu(pipeline.depth_model, device)
    print(f"  [offload] Running depth estimation ... (GPU: {_gpu_mem()})")
    with torch.no_grad(), device:
        pointmap_dict = pipeline.compute_pointmap(image_rgba)

    # Move depth model and results to CPU
    print("  [offload] Moving depth model to CPU ...")
    _offload_to_cpu(pipeline.depth_model)
    pointmap_cpu = pointmap_dict["pointmap"].cpu()
    from sam3d_objects.pipeline.inference_pipeline_pointmap import InferencePipelinePointMap
    pts = InferencePipelinePointMap._down_sample_img(pointmap_cpu)
    pts_colors = InferencePipelinePointMap._down_sample_img(pointmap_dict["pts_color"].cpu())
    for k, v in pointmap_dict.items():
        if hasattr(v, 'cpu'):
            pointmap_dict[k] = v.cpu()
    del pointmap_dict
    gc.collect()
    torch.cuda.empty_cache()
    print(f"  [offload] After depth cleanup: GPU {_gpu_mem()}")

    # --- Stage 1a: Preprocess images + pre-compute condition embeddings ---
    # Load only the condition embedder (2.36 GiB) to compute embeddings
    ss_emb = pipeline.condition_embedders.get("ss_condition_embedder")
    slat_emb = pipeline.condition_embedders.get("slat_condition_embedder")

    print("  [offload] Loading SS condition embedder to GPU for preprocessing ...")
    if ss_emb is not None:
        _offload_to_gpu(ss_emb, device)
    torch.cuda.empty_cache()
    print(f"  [offload] After loading SS embedder: GPU {_gpu_mem()}")

    with torch.no_grad(), device:
        ss_input_dict = pipeline.preprocess_image(
            image_rgba, pipeline.ss_preprocessor, pointmap=pointmap_cpu.to(device)
        )
        # Pre-compute SS condition embeddings
        ss_cond_args, ss_cond_kwargs = pipeline.get_condition_input(
            ss_emb, ss_input_dict, pipeline.ss_condition_input_mapping,
        )
        # Cache the embeddings on GPU (small tensor)
        ss_cached_tokens = ss_cond_args[0] if ss_cond_args else None

    # Move SS embedder to CPU, load SLAT embedder for its preprocessing
    _offload_to_cpu(ss_emb)
    gc.collect()
    torch.cuda.empty_cache()

    if slat_emb is not None:
        _offload_to_gpu(slat_emb, device)
    torch.cuda.empty_cache()

    with torch.no_grad(), device:
        slat_input_dict = pipeline.preprocess_image(image_rgba, pipeline.slat_preprocessor)
        # Pre-compute SLAT condition embeddings
        slat_cond_args, slat_cond_kwargs = pipeline.get_condition_input(
            slat_emb, slat_input_dict, pipeline.slat_condition_input_mapping,
        )
        slat_cached_tokens = slat_cond_args[0] if slat_cond_args else None

    _offload_to_cpu(slat_emb)
    gc.collect()
    torch.cuda.empty_cache()
    print(f"  [offload] After embedding precompute: GPU {_gpu_mem()}")

    # Swap in cached embedders so sample_sparse_structure/sample_slat use them
    orig_ss_emb = pipeline.condition_embedders["ss_condition_embedder"]
    orig_slat_emb = pipeline.condition_embedders["slat_condition_embedder"]
    pipeline.condition_embedders["ss_condition_embedder"] = _CachedEmbedder(ss_cached_tokens).to(device)
    pipeline.condition_embedders["slat_condition_embedder"] = _CachedEmbedder(slat_cached_tokens).to(device)

    # --- Stage 1b: Sparse Structure sampling ---
    print("  [offload] Loading SS generator + decoder to GPU ...")
    _offload_to_gpu(pipeline.models["ss_generator"], device)
    _offload_to_gpu(pipeline.models["ss_decoder"], device)
    torch.cuda.empty_cache()
    print(f"  [offload] After loading SS models: GPU {_gpu_mem()}")

    with torch.no_grad(), device:
        if seed is not None:
            torch.manual_seed(seed)

        print("  [offload] Running sparse structure sampling ...")
        ss_return_dict = pipeline.sample_sparse_structure(
            ss_input_dict, inference_steps=None
        )

        pointmap_scale = ss_input_dict.get("pointmap_scale", None)
        pointmap_shift = ss_input_dict.get("pointmap_shift", None)
        ss_return_dict.update(
            pipeline.pose_decoder(
                ss_return_dict,
                scene_scale=pointmap_scale,
                scene_shift=pointmap_shift,
            )
        )
        ss_return_dict["scale"] = ss_return_dict["scale"] * ss_return_dict["downsample_factor"]
        coords = ss_return_dict["coords"]

    # --- Stage 2: SLAT sampling ---
    print("  [offload] Moving SS models to CPU, loading SLAT generator ...")
    _offload_to_cpu(pipeline.models["ss_generator"])
    _offload_to_cpu(pipeline.models["ss_decoder"])
    gc.collect()
    torch.cuda.empty_cache()

    _offload_to_gpu(pipeline.models["slat_generator"], device)
    torch.cuda.empty_cache()
    print(f"  [offload] After loading SLAT generator: GPU {_gpu_mem()}")

    with torch.no_grad(), device:
        print("  [offload] Running SLAT generation ...")
        slat = pipeline.sample_slat(slat_input_dict, coords, inference_steps=None)

    # --- Stage 3: Gaussian decoding ---
    print("  [offload] Moving SLAT generator to CPU, loading GS decoder ...")
    _offload_to_cpu(pipeline.models["slat_generator"])
    gc.collect()
    torch.cuda.empty_cache()

    _offload_to_gpu(pipeline.models["slat_decoder_gs"], device)
    torch.cuda.empty_cache()

    with torch.no_grad(), device:
        print("  [offload] Decoding Gaussian splat ...")
        outputs = pipeline.decode_slat(slat, ["gaussian"])
        outputs = pipeline.postprocess_slat_output(
            outputs,
            with_mesh_postprocess=False,
            with_texture_baking=False,
            use_vertex_color=True,
        )

    # Restore original embedders
    pipeline.condition_embedders["ss_condition_embedder"] = orig_ss_emb
    pipeline.condition_embedders["slat_condition_embedder"] = orig_slat_emb

    return {
        **ss_return_dict,
        **outputs,
        "pointmap": pts.cpu().permute((1, 2, 0)),
        "pointmap_colors": pts_colors.cpu().permute((1, 2, 0)),
    }


def main():
    parser = argparse.ArgumentParser(description="SAM 3D Objects single-object demo")
    parser.add_argument(
        "--image-dir",
        default=os.path.join(SAM3D_ROOT, "notebook", "images", "shutterstock_stylish_kidsroom_1640806567"),
        help="Directory containing image.png and mask PNGs",
    )
    parser.add_argument("--mask-index", type=int, default=14, help="Mask index to use")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--checkpoint-tag", default="", help="Checkpoint tag (subdir under checkpoints/)"
    )
    parser.add_argument("--output-dir", default="output", help="Output directory for results")
    parser.add_argument("--resolution", type=int, default=512, help="Render resolution")
    parser.add_argument("--num-frames", type=int, default=120, help="Number of frames in GIF")
    parser.add_argument(
        "--offload", action="store_true",
        help="Enable CPU offloading to reduce GPU memory (needed for GPUs with <24GB VRAM)",
    )
    args = parser.parse_args()

    # Resolve paths
    image_path = os.path.join(args.image_dir, "image.png")
    image_name = os.path.basename(args.image_dir)
    config_path = os.path.join(SAM3D_ROOT, "checkpoints", args.checkpoint_tag, "pipeline.yaml")
    os.makedirs(args.output_dir, exist_ok=True)

    # Validate inputs
    if not os.path.exists(image_path):
        print(f"Error: Image not found at {image_path}")
        sys.exit(1)
    if not os.path.exists(config_path):
        print(f"Error: Config not found at {config_path}")
        print("Download checkpoints first:")
        print("  huggingface-cli download --repo-type model --local-dir checkpoints/hf-download facebook/sam-3d-objects")
        sys.exit(1)

    # 1. Load model
    init_device = "cpu" if args.offload else "cuda"
    print(f"Loading model from {config_path} (device={init_device}) ...")
    inference = Inference(config_path, compile=False, device=init_device)

    # 2. Load image and mask
    print(f"Loading image: {image_path}")
    print(f"Using mask index: {args.mask_index}")
    image = load_image(image_path)
    mask = load_single_mask(args.image_dir, index=args.mask_index)

    # 3. Run inference
    print("Running inference ...")
    if args.offload:
        print("(CPU offloading enabled)")
        output = run_with_offloading(inference, image, mask, seed=args.seed)
    else:
        output = inference(image, mask, seed=args.seed)

    # 4. Save Gaussian splat as PLY
    ply_path = os.path.join(args.output_dir, f"{image_name}.ply")
    output["gs"].save_ply(ply_path)
    print(f"Saved Gaussian splat: {ply_path}")

    # 5. Render rotating GIF
    print(f"Rendering {args.num_frames}-frame video at {args.resolution}px ...")

    # Free all pipeline models from GPU before rendering
    if args.offload:
        pipeline = inference._pipeline
        _offload_to_cpu(pipeline.models)
        _offload_to_cpu(pipeline.depth_model)
        for emb in pipeline.condition_embedders.values():
            _offload_to_cpu(emb)
        torch.cuda.empty_cache()

    try:
        import imageio

        scene_gs = make_scene(output)
        scene_gs = ready_gaussian_for_video_rendering(scene_gs)

        video = render_video(
            scene_gs,
            r=1,
            fov=60,
            pitch_deg=15,
            yaw_start_deg=-45,
            resolution=args.resolution,
            num_frames=args.num_frames,
        )["color"]

        gif_path = os.path.join(args.output_dir, f"{image_name}.gif")
        imageio.mimsave(gif_path, video, format="GIF", duration=1000 / 30, loop=0)
        print(f"Saved GIF: {gif_path}")
    except Exception as e:
        print(f"Warning: GIF rendering failed ({e})")
        print("The Gaussian splat PLY was saved successfully and can be viewed in a 3D viewer.")

    print("\nDone!")


if __name__ == "__main__":
    main()
