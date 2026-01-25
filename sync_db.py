#!/usr/bin/env python3
"""
Sync the literature review database to DigitalOcean Spaces (S3-compatible).

Usage:
    uv run python sync_db.py push          # Upload database with timestamp
    uv run python sync_db.py pull          # Download the latest backup
    uv run python sync_db.py list          # List all backups
    uv run python sync_db.py delete <key>  # Delete a specific backup

Environment variables required:
    DO_SPACES_KEY       - DigitalOcean Spaces access key
    DO_SPACES_SECRET    - DigitalOcean Spaces secret key
"""

import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import boto3

# Load .env file from script directory
load_dotenv(Path(__file__).parent / ".env")
from botocore.exceptions import ClientError

DB_FILE = Path(__file__).parent / "lit_review.db"
BACKUP_PREFIX = "thesis-lit-review/"

# DigitalOcean Spaces configuration
DEFAULT_REGION = "sfo3"
DEFAULT_BUCKET = "blaine-share"


def get_s3_client():
    """Create an S3 client configured for DigitalOcean Spaces."""
    region = os.environ.get("DO_SPACES_REGION", DEFAULT_REGION)
    key = os.environ.get("DO_SPACES_KEY")
    secret = os.environ.get("DO_SPACES_SECRET")

    if not key or not secret:
        print("Error: Missing credentials.")
        print("\nSet these environment variables:")
        print("  export DO_SPACES_KEY='your-access-key'")
        print("  export DO_SPACES_SECRET='your-secret-key'")
        sys.exit(1)

    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://{region}.digitaloceanspaces.com",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
    )


def get_bucket():
    return os.environ.get("DO_SPACES_BUCKET", DEFAULT_BUCKET)


def push():
    """Upload the database with a timestamp."""
    if not DB_FILE.exists():
        print(f"Error: Database file not found: {DB_FILE}")
        sys.exit(1)

    # Create a timestamped copy
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    key = f"{BACKUP_PREFIX}lit_review_{timestamp}.db"

    s3 = get_s3_client()
    bucket = get_bucket()

    # Copy the database to avoid issues with open connections
    tmp_copy = DB_FILE.with_suffix(".db.upload")
    shutil.copy2(DB_FILE, tmp_copy)

    try:
        print(f"Uploading {DB_FILE} to {bucket}/{key}...")
        s3.upload_file(str(tmp_copy), bucket, key)
        print(f"Uploaded successfully: {key}")

        # Get file size for confirmation
        response = s3.head_object(Bucket=bucket, Key=key)
        size_kb = response["ContentLength"] / 1024
        print(f"Size: {size_kb:.1f} KB")
    finally:
        tmp_copy.unlink(missing_ok=True)


def list_backups():
    """List all available backups."""
    s3 = get_s3_client()
    bucket = get_bucket()

    try:
        response = s3.list_objects_v2(Bucket=bucket, Prefix=BACKUP_PREFIX)
    except ClientError as e:
        print(f"Error listing backups: {e}")
        sys.exit(1)

    contents = response.get("Contents", [])
    # Filter out folder entries (size 0 or keys ending with /)
    contents = [
        obj for obj in contents
        if obj.get("Size", 0) > 0 and not obj["Key"].endswith("/")
    ]

    if not contents:
        print("No backups found.")
        return []

    # Sort by last modified (newest first)
    contents.sort(key=lambda x: x["LastModified"], reverse=True)

    print(f"{'Key':<50} {'Size':>10} {'Last Modified'}")
    print("-" * 80)
    for obj in contents:
        key = obj["Key"]
        size = f"{obj['Size'] / 1024:.1f} KB"
        modified = obj["LastModified"].strftime("%Y-%m-%d %H:%M:%S")
        print(f"{key:<50} {size:>10} {modified}")

    return contents


def pull():
    """Download the latest backup."""
    s3 = get_s3_client()
    bucket = get_bucket()

    try:
        response = s3.list_objects_v2(Bucket=bucket, Prefix=BACKUP_PREFIX)
    except ClientError as e:
        print(f"Error listing backups: {e}")
        sys.exit(1)

    contents = response.get("Contents", [])
    # Filter out folder entries (size 0 or keys ending with /)
    contents = [
        obj for obj in contents
        if obj.get("Size", 0) > 0 and not obj["Key"].endswith("/")
    ]

    if not contents:
        print("No backups found to pull.")
        sys.exit(1)

    # Get the most recent backup
    contents.sort(key=lambda x: x["LastModified"], reverse=True)
    latest = contents[0]
    key = latest["Key"]

    print(f"Downloading latest backup: {key}")
    print(f"  Last modified: {latest['LastModified']}")
    print(f"  Size: {latest['Size'] / 1024:.1f} KB")

    # Backup existing database if it exists
    if DB_FILE.exists():
        backup_path = DB_FILE.with_suffix(".db.bak")
        print(f"Backing up existing database to {backup_path}")
        shutil.copy2(DB_FILE, backup_path)

    s3.download_file(bucket, key, str(DB_FILE))
    print(f"Downloaded to {DB_FILE}")


def delete(key: str):
    """Delete a specific backup."""
    s3 = get_s3_client()
    bucket = get_bucket()

    # Ensure key has the prefix
    if not key.startswith(BACKUP_PREFIX):
        key = f"{BACKUP_PREFIX}{key}"

    try:
        # Check if it exists first
        s3.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            print(f"Backup not found: {key}")
            sys.exit(1)
        raise

    confirm = input(f"Delete {key}? [y/N]: ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    s3.delete_object(Bucket=bucket, Key=key)
    print(f"Deleted: {key}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "push":
        push()
    elif command == "pull":
        pull()
    elif command == "list":
        list_backups()
    elif command == "delete":
        if len(sys.argv) < 3:
            print("Usage: sync_db.py delete <key>")
            print("Use 'sync_db.py list' to see available backups")
            sys.exit(1)
        delete(sys.argv[2])
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
