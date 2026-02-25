#!/usr/bin/env python3
"""
Initialize an S3-hosted conda channel with empty repodata.json files.

Run this once before the first build to create the channel structure.
Subsequent uploads via `rattler-build publish` handle indexing automatically.

Usage:
    python scripts/init_s3_channel.py
"""

import json
import os
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()

SUBDIRS = ["noarch", "linux-64", "linux-aarch64", "osx-64", "osx-arm64", "win-64"]
EMPTY_REPODATA = json.dumps({"packages": {}, "packages.conda": {}})


def main():
    bucket = os.environ.get("S3_BUCKET", "wv-forge/wv-forge")
    region = os.environ.get("S3_REGION", "us-east-2")

    print(f"Initializing S3 channel: s3://{bucket}")
    print(f"Region: {region}")
    print()

    env = os.environ.copy()
    env.setdefault("AWS_ACCESS_KEY_ID", env.get("S3_ACCESS_KEY_ID", ""))
    env.setdefault("AWS_SECRET_ACCESS_KEY", env.get("S3_SECRET_ACCESS_KEY", ""))
    env.setdefault("AWS_DEFAULT_REGION", region)

    for subdir in SUBDIRS:
        key = f"s3://{bucket}/{subdir}/repodata.json"
        print(f"  Creating {subdir}/repodata.json ...", end=" ")

        result = subprocess.run(
            ["aws", "s3", "cp", "-", key, "--content-type", "application/json", "--region", region],
            input=EMPTY_REPODATA.encode(),
            env=env,
            capture_output=True,
        )

        if result.returncode == 0:
            print("ok")
        else:
            print("FAILED")
            print(f"    {result.stderr.decode().strip()}")
            sys.exit(1)

    print()
    print(f"Channel s3://{bucket} initialized successfully.")
    print("You can now run builds that resolve from this channel.")


if __name__ == "__main__":
    main()
