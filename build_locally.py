#!/usr/bin/env python3
"""
build_locally.py -- Build wv-forge conda packages in Docker with rattler-build.

Usage:
    python build_locally.py                    # Interactive package selection
    python build_locally.py --all              # Build all packages
    python build_locally.py -p cumm spconv     # Build specific packages
    python build_locally.py --noarch-only      # Build only noarch packages
    python build_locally.py --variant-only     # Build only variant (CUDA) packages
    python build_locally.py --clean             # Remove built outputs, then rebuild all
    python build_locally.py --clean -p cumm     # Clean and rebuild specific packages
    python build_locally.py --dry-run           # Show Docker command without running

Packages are built inside a Docker container using the conda-forge alma9 image.
Output goes to ./output/ (mounted from host). sccache is enabled by default
with the host's ~/.cache/sccache mounted into the container for persistence.
"""

import os
import re
import shutil
import subprocess
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

DOCKER_IMAGE_DEFAULT = "quay.io/condaforge/linux-anvil-x86_64:alma9"
CONTAINER_REPO = "/home/conda/wv-forge"
CONTAINER_SCRIPT = f"{CONTAINER_REPO}/.scripts/run_rattler_build.sh"

# Colors
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
NC = "\033[0m"


@dataclass
class Package:
    name: str
    recipe_dir: str  # Relative to repo root, e.g. "pkgs/cumm/recipe"
    build_type: str  # "noarch", "variant", or "standard"


def discover_packages(repo_root: Path) -> list[Package]:
    """Scan pkgs/ for recipe.yaml files and detect build type."""
    pkgs_dir = repo_root / "pkgs"
    packages = []

    for entry in sorted(pkgs_dir.iterdir()):
        if not entry.is_dir():
            continue

        # Check for recipe/recipe.yaml first, then recipe.yaml at top level
        recipe_path = entry / "recipe" / "recipe.yaml"
        if recipe_path.exists():
            recipe_dir = str((entry / "recipe").relative_to(repo_root))
        else:
            recipe_path = entry / "recipe.yaml"
            if recipe_path.exists():
                recipe_dir = str(entry.relative_to(repo_root))
            else:
                continue

        build_type = detect_build_type(recipe_path)
        packages.append(Package(name=entry.name, recipe_dir=recipe_dir, build_type=build_type))

    return packages


def detect_build_type(recipe_path: Path) -> str:
    """Detect build type from recipe.yaml contents."""
    content = recipe_path.read_text()

    # Check for noarch in build section
    if re.search(r"^\s+noarch:", content, re.MULTILINE):
        return "noarch"

    # Check for variant config with cuda_version
    if "cuda_version" in content:
        return "variant"

    return "standard"


def get_variant_count(repo_root: Path) -> int:
    """Count expected variant builds from variants.yaml (product of all list lengths)."""
    variants_file = repo_root / "variants.yaml"
    if not variants_file.exists():
        return 1
    lists = []
    current_count = 0
    for line in variants_file.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if stripped.startswith("- "):
            current_count += 1
        elif stripped.endswith(":"):
            if current_count > 0:
                lists.append(current_count)
            current_count = 0
    if current_count > 0:
        lists.append(current_count)
    result = 1
    for n in lists:
        result *= n
    return result


def is_package_built(pkg: Package, output_dir: Path, variant_count: int) -> bool:
    """Check if a package already has build outputs in the output directory.

    For noarch/standard packages, checks for at least one matching .conda file.
    For variant packages, checks that all expected variants are present.
    """
    if pkg.build_type == "noarch":
        subdir = output_dir / "noarch"
    else:
        subdir = output_dir / "linux-64"

    if not subdir.exists():
        return False

    matches = list(subdir.glob(f"{pkg.name}-*.conda"))
    if pkg.build_type == "variant":
        return len(matches) >= variant_count
    return len(matches) >= 1


def clean_output(output_dir: Path):
    """Remove built package outputs (preserves src_cache and bld for faster rebuilds)."""
    for subdir_name in ("linux-64", "noarch", "broken"):
        subdir = output_dir / subdir_name
        if subdir.exists():
            shutil.rmtree(subdir)
            print(f"  Removed {subdir}")


def interactive_select(packages: list[Package], output_dir: Path, variant_count: int) -> list[Package]:
    """Present numbered list grouped by type and get user selection."""
    groups = {"noarch": [], "variant": [], "standard": []}
    for pkg in packages:
        groups[pkg.build_type].append(pkg)

    # Build ordered display list
    display = []
    group_labels = {
        "noarch": f"{CYAN}Noarch packages:{NC}",
        "variant": f"{CYAN}Variant packages (CUDA):{NC}",
        "standard": f"{CYAN}Standard packages:{NC}",
    }

    for build_type in ("noarch", "variant", "standard"):
        if groups[build_type]:
            display.append(("header", group_labels[build_type]))
            for pkg in groups[build_type]:
                display.append(("pkg", pkg))

    print(f"\n{BOLD}=== wv-forge Local Builder ==={NC}\n")

    idx = 0
    index_map = {}  # 1-based index -> Package
    for item_type, item in display:
        if item_type == "header":
            print(f"  {item}")
        else:
            idx += 1
            index_map[idx] = item
            built = is_package_built(item, output_dir, variant_count)
            status = f" {GREEN}(built){NC}" if built else ""
            print(f"    {idx:>2}. {item.name}{status}")

    print(f"\n  {BOLD}Shortcuts:{NC} 'all', 'noarch', 'variant', 'standard'")
    print(f"  {BOLD}Examples:{NC}  '1,3,6-8' or 'all'\n")

    try:
        selection = input(f"  Select packages > ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\nAborted.")
        sys.exit(1)

    if not selection:
        print("No selection made.")
        sys.exit(1)

    # Handle keyword shortcuts
    if selection.lower() == "all":
        return packages
    if selection.lower() in ("noarch", "variant", "standard"):
        return [p for p in packages if p.build_type == selection.lower()]

    # Parse numeric selection
    indices = parse_selection(selection, idx)
    selected = []
    for i in indices:
        if i in index_map:
            selected.append(index_map[i])
        else:
            print(f"{RED}Invalid index: {i}{NC}", file=sys.stderr)
            sys.exit(1)

    return selected


def parse_selection(selection: str, total: int) -> list[int]:
    """Parse '1,3,6-8' into list of 1-based indices."""
    indices = []
    for part in selection.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            start, end = int(start.strip()), int(end.strip())
            indices.extend(range(start, end + 1))
        else:
            indices.append(int(part))
    return indices


def build_docker_command(
    packages: list[Package],
    repo_root: Path,
    docker_image: str,
    no_sccache: bool,
    jobs: int | None = None,
) -> list[str]:
    """Construct the docker run command."""
    # Encode package specs as semicolon-delimited "type:name:container_recipe_dir"
    specs = []
    for pkg in packages:
        container_recipe = f"{CONTAINER_REPO}/{pkg.recipe_dir}"
        specs.append(f"{pkg.build_type}:{pkg.name}:{container_recipe}")
    package_spec_string = ";".join(specs)

    output_dir = repo_root / "output"
    sccache_dir = Path.home() / ".cache" / "sccache"
    rattler_cache_dir = Path.home() / ".cache" / "rattler"

    cmd = ["docker", "run", "--rm", "--network", "host"]

    # Add -it only when stdin is a TTY
    if sys.stdin.isatty():
        cmd.append("-it")

    # Mount repo read-only
    cmd.extend(["-v", f"{repo_root}:{CONTAINER_REPO}:ro"])

    # Mount output directory read-write (overlays the ro mount)
    cmd.extend(["-v", f"{output_dir}:{CONTAINER_REPO}/output"])

    # Mount rattler cache for repodata caching across builds
    cmd.extend(["-v", f"{rattler_cache_dir}:/home/conda/.cache/rattler"])

    # Mount sccache cache
    if not no_sccache:
        cmd.extend(["-v", f"{sccache_dir}:/home/conda/.cache/sccache"])

    # Environment variables
    cmd.extend(["-e", f"BUILD_PACKAGES={package_spec_string}"])
    cmd.extend(["-e", f"SCCACHE_ENABLED={'0' if no_sccache else '1'}"])
    cmd.extend(["-e", f"HOST_USER_ID={os.getuid()}"])
    cmd.extend(["-e", f"BUILD_JOBS={jobs}"])

    # Forward CONDA_OVERRIDE_CUDA so the solver can resolve __cuda deps in
    # GPU-less Docker builds.  run_rattler_build.sh defaults to 12.9 when unset.
    cuda_override = os.environ.get("CONDA_OVERRIDE_CUDA")
    if cuda_override:
        cmd.extend(["-e", f"CONDA_OVERRIDE_CUDA={cuda_override}"])

    # Forward channel and S3 config so the container can resolve deps and auth
    for env_var in ("WV_FORGE_CHANNEL_URL", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_REGION"):
        val = os.environ.get(env_var)
        if val:
            cmd.extend(["-e", f"{env_var}={val}"])

    # Image and command
    cmd.append(docker_image)
    cmd.extend(["bash", CONTAINER_SCRIPT])

    return cmd


def main():
    parser = ArgumentParser(
        description="Build wv-forge conda packages in Docker with rattler-build"
    )
    parser.add_argument(
        "--packages", "-p", nargs="+", metavar="PKG",
        help="Package names to build (non-interactive)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Build all packages",
    )
    parser.add_argument(
        "--noarch-only", action="store_true",
        help="Build only noarch packages",
    )
    parser.add_argument(
        "--variant-only", action="store_true",
        help="Build only variant (CUDA) packages",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Remove built outputs and rebuild from scratch",
    )
    parser.add_argument(
        "--jobs", "-j", type=int, default=28, metavar="N",
        help="Max parallel compilation jobs (default: 28)",
    )
    parser.add_argument(
        "--no-sccache", action="store_true",
        help="Disable sccache",
    )
    parser.add_argument(
        "--docker-image", default=DOCKER_IMAGE_DEFAULT,
        help=f"Docker image to use (default: {DOCKER_IMAGE_DEFAULT})",
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Print the docker command without running it",
    )
    parser.add_argument(
        "--no-upload", action="store_true",
        help="Skip uploading packages to S3 after build",
    )
    parser.add_argument(
        "--force", "-f", action="store_true",
        help="Overwrite existing packages on S3 during upload",
    )

    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent
    output_dir = repo_root / "output"
    variant_count = get_variant_count(repo_root)

    # Discover packages
    packages = discover_packages(repo_root)
    if not packages:
        print(f"{RED}No packages found in pkgs/{NC}", file=sys.stderr)
        sys.exit(1)

    # Handle --clean: remove built outputs before selecting
    if args.clean:
        if args.dry_run:
            print(f"\n{YELLOW}[DRY RUN] Would clean built outputs from:{NC}")
            for subdir_name in ("linux-64", "noarch", "broken"):
                subdir = output_dir / subdir_name
                if subdir.exists():
                    print(f"  {subdir}")
            print()
        else:
            print(f"\n{YELLOW}Cleaning built outputs...{NC}")
            clean_output(output_dir)
            print()

    # Select packages
    if args.all:
        selected = packages
    elif args.noarch_only:
        selected = [p for p in packages if p.build_type == "noarch"]
    elif args.variant_only:
        selected = [p for p in packages if p.build_type == "variant"]
    elif args.packages:
        pkg_names = set(args.packages)
        selected = [p for p in packages if p.name in pkg_names]
        unknown = pkg_names - {p.name for p in selected}
        if unknown:
            print(f"{RED}Unknown packages: {', '.join(sorted(unknown))}{NC}", file=sys.stderr)
            print(f"Available: {', '.join(p.name for p in packages)}", file=sys.stderr)
            sys.exit(1)
    else:
        selected = interactive_select(packages, output_dir, variant_count)

    if not selected:
        print("No packages selected.")
        sys.exit(0)

    # Skip already-built packages (unless --clean already wiped them)
    if not args.clean:
        to_build = []
        skipped = []
        for pkg in selected:
            if is_package_built(pkg, output_dir, variant_count):
                skipped.append(pkg)
            else:
                to_build.append(pkg)

        if skipped:
            print(f"\n{YELLOW}Skipping {len(skipped)} already-built package(s):{NC}")
            for pkg in skipped:
                print(f"  - {pkg.name} ({pkg.build_type})")

        selected = to_build

        if not selected:
            print(f"\n{GREEN}All selected packages are already built. Use --clean to rebuild.{NC}")
            sys.exit(0)

    # Show what will be built
    print(f"\n{GREEN}Building {len(selected)} package(s):{NC}")
    for pkg in selected:
        print(f"  - {pkg.name} ({pkg.build_type})")
    print()

    # Ensure host directories exist
    output_dir.mkdir(exist_ok=True)
    rattler_cache_dir = Path.home() / ".cache" / "rattler"
    rattler_cache_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_sccache:
        sccache_dir = Path.home() / ".cache" / "sccache"
        sccache_dir.mkdir(parents=True, exist_ok=True)

    # Build Docker command
    cmd = build_docker_command(selected, repo_root, args.docker_image, args.no_sccache, args.jobs)

    if args.dry_run:
        print(f"{YELLOW}[DRY RUN] Docker command:{NC}")
        # Pretty-print the command with line continuations
        print("  docker run \\")
        # Skip "docker" and "run", format the rest
        i = 2
        while i < len(cmd):
            arg = cmd[i]
            if arg in ("-v", "-e", "-it", "--rm"):
                if i + 1 < len(cmd) and not cmd[i + 1].startswith("-"):
                    print(f"    {arg} {cmd[i + 1]} \\")
                    i += 2
                else:
                    print(f"    {arg} \\")
                    i += 1
            else:
                if i == len(cmd) - 1:
                    print(f"    {arg}")
                else:
                    print(f"    {arg} \\")
                i += 1
        sys.exit(0)

    # Run Docker build
    print(f"{GREEN}Launching Docker build...{NC}\n")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        sys.exit(result.returncode)

    # Upload packages to S3
    if not args.no_upload:
        print(f"\n{GREEN}Uploading packages to S3...{NC}\n")
        upload_script = repo_root / "scripts" / "upload_to_s3.py"
        upload_cmd = [sys.executable, str(upload_script), "--all", "--output-dir", str(output_dir)]
        if args.force:
            upload_cmd.append("--force")
        upload_result = subprocess.run(upload_cmd)
        if upload_result.returncode != 0:
            print(f"\n{RED}Upload failed (build succeeded). Run manually: pixi run upload{NC}")
            sys.exit(upload_result.returncode)

    sys.exit(0)


if __name__ == "__main__":
    main()
