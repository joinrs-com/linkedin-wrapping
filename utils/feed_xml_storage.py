"""Store / load prebuilt feed XML gzip blobs (S3 or local directory).

Campaign feeds are too large for MySQL max_allowed_packet (~64MiB). Prefer:
  FEED_XML_S3_BUCKET   → s3://bucket/[prefix/]{feed_name}.xml.gz
  FEED_XML_STORAGE_DIR → {dir}/{feed_name}.xml.gz  (local/tests)

If neither is set, callers may fall back to MySQL LONGBLOB (not viable for full-text USA).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator


def s3_bucket() -> str | None:
    b = (os.getenv("FEED_XML_S3_BUCKET") or "").strip()
    return b or None


def s3_prefix() -> str:
    p = (os.getenv("FEED_XML_S3_PREFIX") or "feed-xml").strip().strip("/")
    return p


def local_storage_dir() -> Path | None:
    d = (os.getenv("FEED_XML_STORAGE_DIR") or "").strip()
    return Path(d) if d else None


def object_key(feed_name: str) -> str:
    prefix = s3_prefix()
    name = feed_name.strip().replace("/", "_")
    return f"{prefix}/{name}.xml.gz" if prefix else f"{name}.xml.gz"


def storage_uri_for(feed_name: str) -> str:
    """Canonical URI stored in feed_xml_artifact.storage_uri."""
    bucket = s3_bucket()
    if bucket:
        return f"s3://{bucket}/{object_key(feed_name)}"
    local = local_storage_dir()
    if local:
        return f"file://{(local / f'{feed_name}.xml.gz').resolve()}"
    raise RuntimeError(
        "Set FEED_XML_S3_BUCKET or FEED_XML_STORAGE_DIR to store campaign feed artifacts"
    )


def put_gzip(feed_name: str, payload: bytes) -> str:
    """Write gzip bytes; return storage_uri."""
    bucket = s3_bucket()
    if bucket:
        import boto3

        key = object_key(feed_name)
        boto3.client("s3").put_object(
            Bucket=bucket,
            Key=key,
            Body=payload,
            ContentType="application/gzip",
            ContentEncoding="gzip",
        )
        return f"s3://{bucket}/{key}"

    local = local_storage_dir()
    if local:
        local.mkdir(parents=True, exist_ok=True)
        path = local / f"{feed_name}.xml.gz"
        path.write_bytes(payload)
        return f"file://{path.resolve()}"

    raise RuntimeError(
        "Set FEED_XML_S3_BUCKET or FEED_XML_STORAGE_DIR to store campaign feed artifacts"
    )


def get_gzip(storage_uri: str) -> bytes:
    """Load full gzip payload from s3:// or file:// URI."""
    if storage_uri.startswith("s3://"):
        import boto3

        rest = storage_uri[len("s3://") :]
        bucket, _, key = rest.partition("/")
        if not bucket or not key:
            raise ValueError(f"invalid s3 uri: {storage_uri}")
        obj = boto3.client("s3").get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()

    if storage_uri.startswith("file://"):
        path = Path(storage_uri[len("file://") :])
        return path.read_bytes()

    raise ValueError(f"unsupported storage_uri scheme: {storage_uri}")


def iter_gzip(storage_uri: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    """Stream gzip bytes in chunks (for FastAPI StreamingResponse)."""
    if storage_uri.startswith("s3://"):
        import boto3

        rest = storage_uri[len("s3://") :]
        bucket, _, key = rest.partition("/")
        obj = boto3.client("s3").get_object(Bucket=bucket, Key=key)
        body = obj["Body"]
        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                break
            yield chunk
        return

    if storage_uri.startswith("file://"):
        path = Path(storage_uri[len("file://") :])
        with path.open("rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        return

    raise ValueError(f"unsupported storage_uri scheme: {storage_uri}")


def external_storage_configured() -> bool:
    return bool(s3_bucket() or local_storage_dir())
