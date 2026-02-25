#!/usr/bin/env python3
"""
Upload conda packages to an S3-hosted conda channel using rattler-build publish.

Uses `rattler-build publish` which handles channel initialization, upload,
and repodata indexing in one step.

Usage:
    # Set credentials in .env (see .env.example)

    # Upload all packages from the output directory
    pixi run upload

    # Upload a single package
    python scripts/upload_to_s3.py output/linux-64/cloudcompare-2.13.2-hb0f4dca_0.conda

    # Dry run
    python scripts/upload_to_s3.py --all --dry-run
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

DEFAULT_BUCKET = "wv-forge/wv-forge"
DEFAULT_REGION = "us-east-2"


def get_s3_config() -> dict:
    """Get S3 configuration from environment variables."""
    config = {
        "bucket": os.environ.get("S3_BUCKET", DEFAULT_BUCKET),
        "region": os.environ.get("S3_REGION", DEFAULT_REGION),
        "access_key_id": os.environ.get("S3_ACCESS_KEY_ID"),
        "secret_access_key": os.environ.get("S3_SECRET_ACCESS_KEY"),
    }

    if not config["access_key_id"] or not config["secret_access_key"]:
        print("Error: S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY must be set")
        print("       Set them in .env or as environment variables (see .env.example)")
        sys.exit(1)

    return config


def find_packages(output_dir: Path) -> list[Path]:
    """Find all conda packages in output directory, skipping non-platform subdirs."""
    packages = []
    valid_subdirs = {
        "linux-64", "linux-aarch64", "linux-ppc64le", "linux-s390x",
        "osx-64", "osx-arm64", "win-64", "win-arm64", "noarch",
    }

    for subdir in output_dir.iterdir():
        if subdir.is_dir() and subdir.name in valid_subdirs:
            packages.extend(subdir.glob("*.conda"))
            packages.extend(subdir.glob("*.tar.bz2"))

    return sorted(packages)


def upload_package(filepath: Path, config: dict, force: bool = False) -> bool:
    """
    Publish a single package to S3 using rattler-build publish.

    Returns True if upload succeeded, False otherwise.
    """
    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        return False

    if filepath.suffix not in ['.conda', '.bz2']:
        print(f"Skipping {filepath.name}: not a conda package")
        return False

    size_mb = filepath.stat().st_size / (1024 * 1024)
    channel = f"s3://{config['bucket']}"

    print(f"Publishing {filepath.name} ({size_mb:.2f} MB) to {channel}...")

    cmd = [
        "rattler-build", "publish",
        str(filepath),
        "--to", channel,
    ]
    if force:
        cmd.append("--force")

    # rattler-build publish reads standard AWS env vars for S3 auth
    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = config["access_key_id"]
    env["AWS_SECRET_ACCESS_KEY"] = config["secret_access_key"]
    env["AWS_DEFAULT_REGION"] = config["region"]
    env["AWS_REGION"] = config["region"]
    # Also set S3_* vars for the upload path
    env["S3_ACCESS_KEY_ID"] = config["access_key_id"]
    env["S3_SECRET_ACCESS_KEY"] = config["secret_access_key"]

    result = subprocess.run(cmd, env=env)

    if result.returncode == 0:
        print(f"  Successfully published {filepath.name}")
        return True
    else:
        print(f"  Publish failed for {filepath.name}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Publish conda packages to S3 channel via rattler-build",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload a single package
  %(prog)s output/linux-64/mypackage-1.0-h123_0.conda

  # Upload all packages from output/
  %(prog)s --all

  # Upload to a different bucket
  %(prog)s --bucket my-other-bucket --all

Environment:
  S3_ACCESS_KEY_ID       Your AWS access key ID (required)
  S3_SECRET_ACCESS_KEY   Your AWS secret access key (required)
  S3_BUCKET              S3 bucket/channel path (default: wv-forge/wv-forge)
  S3_REGION              AWS region (default: us-east-2)
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
        "--bucket", "-b",
        default=None,
        help=f"S3 bucket/channel path (default: from S3_BUCKET env or '{DEFAULT_BUCKET}')"
    )
    parser.add_argument(
        "--region",
        default=None,
        help=f"AWS region (default: from S3_REGION env or '{DEFAULT_REGION}')"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=Path("output"),
        help="Output directory containing packages (default: output/)"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing packages on S3"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be uploaded without actually uploading"
    )

    args = parser.parse_args()

    # Get S3 config
    config = get_s3_config()

    # CLI overrides for bucket/region
    if args.bucket:
        config["bucket"] = args.bucket
    if args.region:
        config["region"] = args.region

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

    channel = f"s3://{config['bucket']}"
    print(f"Found {len(packages)} package(s)")
    print(f"Target: {channel} (region: {config['region']})")
    print()

    for pkg in packages:
        size_mb = pkg.stat().st_size / (1024 * 1024)
        print(f"  - {pkg.parent.name}/{pkg.name} ({size_mb:.2f} MB)")
    print()

    if args.dry_run:
        print("Dry run - no packages uploaded")
        sys.exit(0)

    # Upload packages
    success = 0
    failed = 0

    for pkg in packages:
        if upload_package(pkg, config, force=args.force):
            success += 1
        else:
            failed += 1

    print()
    print(f"Upload complete: {success} succeeded, {failed} failed")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
