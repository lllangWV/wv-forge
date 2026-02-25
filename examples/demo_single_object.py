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

# inference.py sets these, but set early just in case
os.environ["LIDRA_SKIP_INIT"] = "true"

from inference import (
    Inference,
    ready_gaussian_for_video_rendering,
    render_video,
    load_image,
    load_single_mask,
    make_scene,
)

# Path to the sam-3d-objects repo (images, checkpoints)
SAM3D_ROOT = os.path.join(os.path.dirname(__file__), "..", "tmp", "sam-3d-objects")


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
        "--checkpoint-tag", default="hf", help="Checkpoint tag (subdir under checkpoints/)"
    )
    parser.add_argument("--output-dir", default="output", help="Output directory for results")
    parser.add_argument("--resolution", type=int, default=512, help="Render resolution")
    parser.add_argument("--num-frames", type=int, default=120, help="Number of frames in GIF")
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
    print(f"Loading model from {config_path} ...")
    inference = Inference(config_path, compile=False)

    # 2. Load image and mask
    print(f"Loading image: {image_path}")
    print(f"Using mask index: {args.mask_index}")
    image = load_image(image_path)
    mask = load_single_mask(args.image_dir, index=args.mask_index)

    # 3. Run inference
    print("Running inference ...")
    output = inference(image, mask, seed=args.seed)

    # 4. Save Gaussian splat as PLY
    ply_path = os.path.join(args.output_dir, f"{image_name}.ply")
    output["gs"].save_ply(ply_path)
    print(f"Saved Gaussian splat: {ply_path}")

    # 5. Render rotating GIF
    print(f"Rendering {args.num_frames}-frame video at {args.resolution}px ...")
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

    print("\nDone!")


if __name__ == "__main__":
    main()
