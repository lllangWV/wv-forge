#!/usr/bin/env python3
"""
Upload conda packages to prefix.dev channel, skipping packages already on the channel.

Usage:
    # Create a .env file with your API token
    echo 'PREFIX_API_KEY=pfx_your_token_here' > .env

    # Upload a single package
    pixi run upload output/linux-64/cloudcompare-2.13.2-hb0f4dca_0.conda

    # Upload all packages not already on the channel
    pixi run upload-all

    # Force overwrite existing packages
    pixi run upload-force
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Default channel - change this to your channel name
DEFAULT_CHANNEL = "wv-forge"
PREFIX_API_BASE = "https://prefix.dev/api/v1"
PREFIX_CHANNEL_BASE = "https://prefix.dev"


def get_token() -> str:
    """Get API token from environment variable or .env file."""
    token = os.environ.get("PREFIX_API_KEY")
    if not token:
        print("Error: PREFIX_API_KEY not found")
        sys.exit(1)
    return token


def get_remote_packages(channel: str, subdir: str) -> set[str]:
    """Fetch the set of package filenames already on the remote channel for a given subdir."""
    url = f"{PREFIX_CHANNEL_BASE}/{channel}/{subdir}/repodata.json"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            print(f"Warning: Could not fetch repodata for {subdir} (HTTP {response.status_code})")
            return set()

        data = response.json()
        remote = set()
        # .conda packages
        remote.update(data.get("packages.conda", {}).keys())
        # .tar.bz2 packages
        remote.update(data.get("packages", {}).keys())
        return remote

    except requests.exceptions.RequestException as e:
        print(f"Warning: Could not fetch repodata for {subdir}: {e}")
        return set()


def upload_package(filepath: Path, channel: str, token: str, force: bool = False) -> bool:
    """
    Upload a single package to prefix.dev channel.

    Args:
        filepath: Path to the .conda or .tar.bz2 package
        channel: Channel name on prefix.dev
        token: API token
        force: Whether to overwrite existing packages

    Returns:
        True if upload succeeded, False otherwise
    """
    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        return False

    if not filepath.suffix in ['.conda', '.bz2']:
        print(f"Skipping {filepath.name}: not a conda package")
        return False

    data = filepath.read_bytes()
    size_mb = len(data) / (1024 * 1024)

    # Skip if larger than 100MB
    if len(data) > 100 * 1024 * 1024:
        print(f"Skipping {filepath.name}: too large ({size_mb:.1f} MB > 100 MB limit)")
        return False

    # Calculate SHA256 hash
    sha256 = hashlib.sha256(data).hexdigest()

    headers = {
        "X-File-Name": filepath.name,
        "X-File-SHA256": sha256,
        "Authorization": f"Bearer {token}",
        "Content-Length": str(len(data)),
        "Content-Type": "application/octet-stream",
    }

    url = f"{PREFIX_API_BASE}/upload/{channel}"
    if force:
        url += "?force=true"

    print(f"Uploading {filepath.name} ({size_mb:.2f} MB) to {channel}...")

    try:
        response = requests.post(url, data=data, headers=headers, timeout=300)

        if response.status_code == 200:
            print(f"  ✓ Successfully uploaded {filepath.name}")
            return True
        elif response.status_code == 409:
            print(f"  ✗ Package already exists: {filepath.name}")
            print(f"    Use --force to overwrite")
            return False
        else:
            print(f"  ✗ Upload failed with status {response.status_code}")
            print(f"    Response: {response.text}")
            return False

    except requests.exceptions.Timeout:
        print(f"  ✗ Upload timed out for {filepath.name}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  ✗ Upload failed: {e}")
        return False


def find_packages(output_dir: Path) -> list[Path]:
    """Find all conda packages in output directory, skipping non-platform subdirs."""
    packages = []
    # Only look in valid conda subdirs (platform dirs and noarch)
    valid_subdirs = {
        "linux-64", "linux-aarch64", "linux-ppc64le", "linux-s390x",
        "osx-64", "osx-arm64", "win-64", "win-arm64", "noarch",
    }

    for subdir in output_dir.iterdir():
        if subdir.is_dir() and subdir.name in valid_subdirs:
            packages.extend(subdir.glob("*.conda"))
            packages.extend(subdir.glob("*.tar.bz2"))

    return sorted(packages)


def filter_new_packages(packages: list[Path], channel: str) -> tuple[list[Path], list[Path]]:
    """
    Filter packages to only those not already on the remote channel.

    Returns:
        Tuple of (new_packages, skipped_packages)
    """
    # Collect which subdirs we need to check
    subdirs = set()
    for pkg in packages:
        subdirs.add(pkg.parent.name)

    # Fetch remote package lists for each subdir
    remote_packages: dict[str, set[str]] = {}
    for subdir in subdirs:
        print(f"Fetching remote package list for {subdir}...")
        remote_packages[subdir] = get_remote_packages(channel, subdir)

    # Filter
    new_packages = []
    skipped = []
    for pkg in packages:
        subdir = pkg.parent.name
        if pkg.name in remote_packages.get(subdir, set()):
            skipped.append(pkg)
        else:
            new_packages.append(pkg)

    return new_packages, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Upload conda packages to prefix.dev (skips packages already on the channel)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload a single package
  %(prog)s output/linux-64/mypackage-1.0-h123_0.conda

  # Upload all new packages (skips already-uploaded)
  %(prog)s --all

  # Force overwrite existing packages
  %(prog)s --all --force

  # Upload to a different channel
  %(prog)s --channel my-channel --all

Environment:
  PREFIX_API_KEY    Your prefix.dev API token (required)
        """
    )

    parser.add_argument(
        "packages",
        nargs="*",
        type=Path,
        help="Package files to upload"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Upload all packages from output/ directory"
    )
    parser.add_argument(
        "--channel", "-c",
        default=DEFAULT_CHANNEL,
        help=f"Channel name on prefix.dev (default: {DEFAULT_CHANNEL})"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing packages"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=Path("output"),
        help="Output directory containing packages (default: output/)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be uploaded without actually uploading"
    )

    args = parser.parse_args()

    # Get packages to upload
    if args.all:
        if not args.output_dir.exists():
            print(f"Error: Output directory not found: {args.output_dir}")
            sys.exit(1)
        packages = find_packages(args.output_dir)
    elif args.packages:
        packages = args.packages
    else:
        parser.print_help()
        sys.exit(1)

    if not packages:
        print("No packages found to upload")
        sys.exit(1)

    print(f"Found {len(packages)} local package(s)")

    # Filter out packages already on the channel (unless --force)
    if not args.force:
        packages, skipped = filter_new_packages(packages, args.channel)
        if skipped:
            print(f"\nSkipping {len(skipped)} package(s) already on '{args.channel}':")
            for pkg in skipped:
                print(f"  - {pkg.parent.name}/{pkg.name}")
        if not packages:
            print("\nAll packages are already on the channel. Nothing to upload.")
            sys.exit(0)

    print(f"\n{len(packages)} package(s) to upload to '{args.channel}':")
    for pkg in packages:
        size_mb = pkg.stat().st_size / (1024 * 1024)
        print(f"  - {pkg.parent.name}/{pkg.name} ({size_mb:.2f} MB)")
    print()

    if args.dry_run:
        print("Dry run - no packages uploaded")
        sys.exit(0)

    # Get token
    token = get_token()

    # Upload packages
    success = 0
    failed = 0

    for pkg in packages:
        if upload_package(pkg, args.channel, token, args.force):
            success += 1
        else:
            failed += 1

    print()
    print(f"Upload complete: {success} succeeded, {failed} failed")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
