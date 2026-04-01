#!/usr/bin/env python3
"""
Sync the coding app database and PDFs to DigitalOcean Spaces (S3-compatible).

Usage:
    uv run python sync_db.py push          # Upload database + PDFs with timestamp
    uv run python sync_db.py pull          # Download the latest snapshot
    uv run python sync_db.py list          # List all snapshots
    uv run python sync_db.py delete <key>  # Delete a specific snapshot

Environment variables required (from ../.env):
    DO_SPACES_KEY       - DigitalOcean Spaces access key
    DO_SPACES_SECRET    - DigitalOcean Spaces secret key
"""

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env from parent directory (shared with lit-review app)
load_dotenv(Path(__file__).parent.parent / ".env")

import boto3
from botocore.exceptions import ClientError

DB_FILE = Path(__file__).parent / "lit_review.db"
PDF_DIR = Path(__file__).parent / "pdfs"
BACKUP_PREFIX = "thesis-lit-review-coding/"

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
        print("\nSet these environment variables (or add to ../.env):")
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
    """Upload the database and PDFs with a timestamp."""
    if not DB_FILE.exists():
        print(f"Error: Database file not found: {DB_FILE}")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    db_key = f"{BACKUP_PREFIX}lit_review_{timestamp}.db"
    manifest_key = f"{BACKUP_PREFIX}manifest_{timestamp}.json"

    s3 = get_s3_client()
    bucket = get_bucket()

    # Upload database
    tmp_copy = DB_FILE.with_suffix(".db.upload")
    shutil.copy2(DB_FILE, tmp_copy)

    try:
        print(f"Uploading database to {bucket}/{db_key}...")
        s3.upload_file(str(tmp_copy), bucket, db_key)
        response = s3.head_object(Bucket=bucket, Key=db_key)
        print(f"  Database: {response['ContentLength'] / 1024:.1f} KB")
    finally:
        tmp_copy.unlink(missing_ok=True)

    # Upload PDFs
    pdf_keys = []
    if PDF_DIR.exists():
        pdf_files = sorted(PDF_DIR.glob("*.pdf"))
        if pdf_files:
            print(f"Uploading {len(pdf_files)} PDFs...")
            for pdf_file in pdf_files:
                pdf_key = f"{BACKUP_PREFIX}pdfs_{timestamp}/{pdf_file.name}"
                s3.upload_file(str(pdf_file), bucket, pdf_key)
                pdf_keys.append(pdf_key)
                size_kb = pdf_file.stat().st_size / 1024
                print(f"  {pdf_file.name}: {size_kb:.1f} KB")
        else:
            print("No PDFs found in pdfs/ directory.")
    else:
        print("No pdfs/ directory found.")

    # Upload manifest
    manifest = {
        "timestamp": timestamp,
        "db_key": db_key,
        "pdf_keys": pdf_keys,
    }
    s3.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=json.dumps(manifest, indent=2),
        ContentType="application/json",
    )

    print(f"\nSnapshot {timestamp} uploaded successfully.")
    print(f"  Database: 1 file")
    print(f"  PDFs: {len(pdf_keys)} files")


def _get_manifests(s3, bucket):
    """List all manifest files, sorted newest first."""
    try:
        response = s3.list_objects_v2(
            Bucket=bucket, Prefix=f"{BACKUP_PREFIX}manifest_"
        )
    except ClientError as e:
        print(f"Error listing snapshots: {e}")
        sys.exit(1)

    contents = response.get("Contents", [])
    contents = [
        obj
        for obj in contents
        if obj.get("Size", 0) > 0 and obj["Key"].endswith(".json")
    ]
    contents.sort(key=lambda x: x["LastModified"], reverse=True)
    return contents


def list_snapshots():
    """List all available snapshots."""
    s3 = get_s3_client()
    bucket = get_bucket()
    manifests = _get_manifests(s3, bucket)

    if not manifests:
        print("No snapshots found.")
        return

    print(f"{'Timestamp':<20} {'PDFs':>6} {'Modified'}")
    print("-" * 50)

    for obj in manifests:
        # Download and parse manifest to get PDF count
        resp = s3.get_object(Bucket=bucket, Key=obj["Key"])
        manifest = json.loads(resp["Body"].read())
        ts = manifest["timestamp"]
        n_pdfs = len(manifest.get("pdf_keys", []))
        modified = obj["LastModified"].strftime("%Y-%m-%d %H:%M:%S")
        print(f"{ts:<20} {n_pdfs:>6} {modified}")


def pull():
    """Download the latest snapshot (database + PDFs)."""
    s3 = get_s3_client()
    bucket = get_bucket()
    manifests = _get_manifests(s3, bucket)

    if not manifests:
        print("No snapshots found to pull.")
        sys.exit(1)

    # Get the latest manifest
    latest = manifests[0]
    resp = s3.get_object(Bucket=bucket, Key=latest["Key"])
    manifest = json.loads(resp["Body"].read())

    ts = manifest["timestamp"]
    print(f"Pulling snapshot {ts}")
    print(f"  Modified: {latest['LastModified']}")

    # Backup existing database
    if DB_FILE.exists():
        backup_path = DB_FILE.with_suffix(".db.bak")
        print(f"  Backing up existing database to {backup_path.name}")
        shutil.copy2(DB_FILE, backup_path)

    # Download database
    db_key = manifest["db_key"]
    print(f"  Downloading database...")
    s3.download_file(bucket, db_key, str(DB_FILE))
    print(f"  Database restored.")

    # Download PDFs
    pdf_keys = manifest.get("pdf_keys", [])
    if pdf_keys:
        PDF_DIR.mkdir(exist_ok=True)
        print(f"  Downloading {len(pdf_keys)} PDFs...")
        for pdf_key in pdf_keys:
            filename = pdf_key.rsplit("/", 1)[-1]
            local_path = PDF_DIR / filename
            s3.download_file(bucket, pdf_key, str(local_path))
            print(f"    {filename}")
    else:
        print("  No PDFs in this snapshot.")

    print(f"\nSnapshot {ts} restored successfully.")


def delete(timestamp: str):
    """Delete a specific snapshot by timestamp."""
    s3 = get_s3_client()
    bucket = get_bucket()

    # Find the manifest
    manifest_key = f"{BACKUP_PREFIX}manifest_{timestamp}.json"
    try:
        resp = s3.get_object(Bucket=bucket, Key=manifest_key)
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            print(f"Snapshot not found: {timestamp}")
            print("Use 'sync_db.py list' to see available snapshots.")
            sys.exit(1)
        raise

    manifest = json.loads(resp["Body"].read())

    # Collect all keys to delete
    keys_to_delete = [manifest_key, manifest["db_key"]]
    keys_to_delete.extend(manifest.get("pdf_keys", []))

    print(f"Snapshot {timestamp}:")
    print(f"  Database: 1 file")
    print(f"  PDFs: {len(manifest.get('pdf_keys', []))} files")
    print(f"  Total objects to delete: {len(keys_to_delete)}")

    confirm = input("Delete this snapshot? [y/N]: ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    for key in keys_to_delete:
        s3.delete_object(Bucket=bucket, Key=key)

    print(f"Deleted snapshot {timestamp}.")


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
        list_snapshots()
    elif command == "delete":
        if len(sys.argv) < 3:
            print("Usage: sync_db.py delete <timestamp>")
            print("Use 'sync_db.py list' to see available snapshots")
            sys.exit(1)
        delete(sys.argv[2])
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
