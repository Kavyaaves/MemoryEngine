"""Cloud wiring without the cloud: RDS connection strings, and file storage in DynamoDB (faked by moto)."""

import boto3
import pytest
from moto import mock_aws

from app.config import Settings
from app.config.settings import to_async_database_url
from app.media.storage import CHUNK_BYTES, DynamoDBStorage, LocalStorage, create_table

RDS_HOST = "memories.abcdefghijkl.ap-south-1.rds.amazonaws.com"


def test_rds_connection_string_gets_the_async_driver_and_encryption():
    assert to_async_database_url(f"postgresql://postgres:pw@{RDS_HOST}:5432/postgres") == (
        f"postgresql+asyncpg://postgres:pw@{RDS_HOST}:5432/postgres?ssl=require")
    assert to_async_database_url(f"postgres://u:p@{RDS_HOST}/db?ssl=verify-full").endswith("?ssl=verify-full")


def test_local_and_already_async_urls_are_left_alone():
    local = "postgresql+asyncpg://memory:memory@localhost:5432/memory"
    assert to_async_database_url(local) == local
    assert Settings(database_url="postgresql://u:p@localhost/x").database_url == "postgresql+asyncpg://u:p@localhost/x"


async def test_local_storage_links_expire_and_keys_cannot_escape(tmp_path):
    storage = LocalStorage(Settings(local_storage_dir=str(tmp_path), secret_key="s"))
    await storage.put("u1/a.txt", b"hi")
    assert await storage.get("u1/a.txt") == b"hi"
    assert storage.links.verify("u1/a.txt", 4102444800, storage.links.sign("u1/a.txt", 4102444800))
    assert not storage.links.verify("u1/a.txt", 1, storage.links.sign("u1/a.txt", 1))  # expired
    assert (await storage.signed_url("u1/a.txt")).startswith("/api/media/raw?key=u1%2Fa.txt&exp=")
    with pytest.raises(ValueError):
        await storage.get("../outside.txt")


def all_items(table) -> list[dict]:
    """Every item in the table (a scan returns at most 1 MB per page)."""
    page = table.scan()
    items = page["Items"]
    while "LastEvaluatedKey" in page:
        page = table.scan(ExclusiveStartKey=page["LastEvaluatedKey"])
        items += page["Items"]
    return items


@pytest.fixture
def media_table():
    """A fresh fake DynamoDB table, created exactly like the real one."""
    settings = Settings(aws_region="ap-south-1", dynamodb_media_table="media-test", secret_key="s")
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="ap-south-1")
        assert "created" in create_table(settings, dynamodb)
        assert "already exists" in create_table(settings, dynamodb)  # safe to run twice
        yield settings, dynamodb.Table("media-test")


async def test_dynamodb_storage_splits_big_files_into_chunks(media_table):
    settings, table = media_table
    storage = DynamoDBStorage(settings, table=table)
    photo = bytes(range(256)) * 4000  # ~1 MB: needs three chunks
    await storage.put("u1/photos/abc.jpg", photo, "image/jpeg")

    chunks = all_items(table)
    assert sorted(int(item["chunk"]) for item in chunks) == [0, 1, 2]
    assert all(len(item["data"].value) <= CHUNK_BYTES for item in chunks)
    assert await storage.get("u1/photos/abc.jpg") == photo  # reassembled in order

    await storage.delete("u1/photos/abc.jpg")
    assert all_items(table) == []
    with pytest.raises(FileNotFoundError):
        await storage.get("u1/photos/abc.jpg")


async def test_dynamodb_storage_handles_empty_files_and_signed_links(media_table):
    settings, table = media_table
    storage = DynamoDBStorage(settings, table=table)
    await storage.put("u1/uploads/empty.txt", b"")
    assert await storage.get("u1/uploads/empty.txt") == b""
    url = await storage.signed_url("u1/uploads/empty.txt", expires=60)
    assert url.startswith("/api/media/raw?")  # served by our API: the browser can't read DynamoDB
