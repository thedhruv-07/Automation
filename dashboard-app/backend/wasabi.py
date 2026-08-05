"""Archives uploaded Excel rosters to Wasabi (S3-compatible object storage)
and records the archive in MongoDB's uploads collection -- purely an audit
trail; nothing else in the app reads from the uploads collection."""
import os
from datetime import datetime

import boto3
from pymongo.database import Database


def archive_upload(
    db: Database, contents: bytes, filename: str, import_format: str, mode: str, row_count: int,
) -> None:
    """Uploads the raw file bytes to Wasabi and records the archive in
    MongoDB. Never raises -- a Wasabi failure (missing credentials, network
    error, bad bucket) is caught and swallowed, since the client import
    this accompanies has already succeeded by the time this runs, and
    losing one audit copy isn't worth turning a successful import into a
    failed API response. The uploads document is still written even when
    the Wasabi call itself fails, just with wasabi_url set to None."""
    uploaded_at = datetime.now().isoformat()
    safe_timestamp = uploaded_at.replace(":", "-")
    key = f"uploads/{safe_timestamp}_{filename}"

    wasabi_url = None
    try:
        bucket = os.environ["WASABI_BUCKET"]
        endpoint = os.environ["WASABI_ENDPOINT"]
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.environ["WASABI_ACCESS_KEY"],
            aws_secret_access_key=os.environ["WASABI_SECRET_KEY"],
        )
        client.put_object(Bucket=bucket, Key=key, Body=contents)
        wasabi_url = f"{endpoint}/{bucket}/{key}"
    except Exception as exc:
        print(f"Wasabi archive failed for {filename!r}: {exc!r}; continuing without it.")

    db["uploads"].insert_one({
        "uploaded_at": uploaded_at,
        "filename": filename,
        "import_format": import_format,
        "mode": mode,
        "row_count": row_count,
        "wasabi_url": wasabi_url,
    })
