"""Tests for wasabi.py's upload-archival."""
from unittest.mock import patch, MagicMock

from wasabi import archive_upload


def test_archive_upload_records_metadata_and_wasabi_url(mongo_db, monkeypatch):
    monkeypatch.setenv("WASABI_ACCESS_KEY", "key")
    monkeypatch.setenv("WASABI_SECRET_KEY", "secret")
    monkeypatch.setenv("WASABI_BUCKET", "my-bucket")
    monkeypatch.setenv("WASABI_ENDPOINT", "https://s3.us-central-1.wasabisys.com")

    mock_s3 = MagicMock()
    with patch("wasabi.boto3.client", return_value=mock_s3) as mock_boto_client:
        archive_upload(
            mongo_db, b"fake xlsx bytes", "roster.xlsx", "roster", "replace", row_count=5,
        )

    mock_boto_client.assert_called_once_with(
        "s3",
        endpoint_url="https://s3.us-central-1.wasabisys.com",
        aws_access_key_id="key",
        aws_secret_access_key="secret",
    )
    mock_s3.put_object.assert_called_once()
    call_kwargs = mock_s3.put_object.call_args.kwargs
    assert call_kwargs["Bucket"] == "my-bucket"
    assert call_kwargs["Body"] == b"fake xlsx bytes"
    assert call_kwargs["Key"].startswith("uploads/")
    assert call_kwargs["Key"].endswith("_roster.xlsx")

    doc = mongo_db["uploads"].find_one()
    assert doc["filename"] == "roster.xlsx"
    assert doc["import_format"] == "roster"
    assert doc["mode"] == "replace"
    assert doc["row_count"] == 5
    assert doc["wasabi_url"] is not None
    assert doc["wasabi_url"].startswith("https://s3.us-central-1.wasabisys.com/my-bucket/uploads/")
    assert doc["uploaded_at"] is not None


def test_archive_upload_records_null_url_and_continues_when_wasabi_call_fails(mongo_db, monkeypatch):
    monkeypatch.setenv("WASABI_ACCESS_KEY", "key")
    monkeypatch.setenv("WASABI_SECRET_KEY", "secret")
    monkeypatch.setenv("WASABI_BUCKET", "my-bucket")
    monkeypatch.setenv("WASABI_ENDPOINT", "https://s3.us-central-1.wasabisys.com")

    mock_s3 = MagicMock()
    mock_s3.put_object.side_effect = Exception("network error")
    with patch("wasabi.boto3.client", return_value=mock_s3):
        archive_upload(
            mongo_db, b"fake xlsx bytes", "roster.xlsx", "roster", "replace", row_count=5,
        )  # must not raise

    doc = mongo_db["uploads"].find_one()
    assert doc["filename"] == "roster.xlsx"
    assert doc["wasabi_url"] is None


def test_archive_upload_records_null_url_and_continues_when_env_vars_missing(mongo_db, monkeypatch):
    monkeypatch.delenv("WASABI_ACCESS_KEY", raising=False)
    monkeypatch.delenv("WASABI_SECRET_KEY", raising=False)
    monkeypatch.delenv("WASABI_BUCKET", raising=False)
    monkeypatch.delenv("WASABI_ENDPOINT", raising=False)

    archive_upload(
        mongo_db, b"fake xlsx bytes", "roster.xlsx", "roster", "merge", row_count=3,
    )  # must not raise

    doc = mongo_db["uploads"].find_one()
    assert doc["filename"] == "roster.xlsx"
    assert doc["mode"] == "merge"
    assert doc["row_count"] == 3
    assert doc["wasabi_url"] is None
