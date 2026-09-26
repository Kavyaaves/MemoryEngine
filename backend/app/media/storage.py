"""Where file bytes live (PLAN §27). PostgreSQL only stores the object *key*.

Pick one with STORAGE_BACKEND:
    DynamoDBStorage  an Amazon DynamoDB table — AWS's always-free tier includes 25 GB of storage
    LocalStorage     a folder on disk (development and tests)

Keys look like: {user_id}/{uploads|photos|audio|video}/{sha256}{.ext}
Using the content hash as the name means the same file is only ever stored once.

Neither backend can be reached from the browser, so to show a photo the API hands out a signed
link to itself (/api/media/raw, see app/api/media.py) that works for a few minutes only.

Create the DynamoDB table once with:
    python -m app.media.storage create-table
"""

import asyncio
import hashlib
import hmac
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import urlencode

import boto3
from boto3.dynamodb.conditions import Key

from app.config import Settings, get_settings

LINK_LIFETIME_SECONDS = 900
# DynamoDB refuses items over 400 KB, so files are stored in chunks with room left for the keys.
CHUNK_BYTES = 350 * 1024


class SignedLinks:
    """Short-lived links to /api/media/raw. The HMAC signature proves this API made the link."""

    def __init__(self, secret_key: str):
        self.secret = secret_key.encode()

    def sign(self, key: str, expires_at: int) -> str:
        return hmac.new(self.secret, f"{key}:{expires_at}".encode(), hashlib.sha256).hexdigest()

    def verify(self, key: str, expires_at: int, signature: str) -> bool:
        return expires_at > time.time() and hmac.compare_digest(self.sign(key, expires_at), signature)

    def url(self, key: str, expires: int = LINK_LIFETIME_SECONDS) -> str:
        expires_at = int(time.time()) + expires
        query = urlencode({"key": key, "exp": expires_at, "sig": self.sign(key, expires_at)})
        return f"/api/media/raw?{query}"


class Storage(Protocol):
    links: SignedLinks

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def signed_url(self, key: str, expires: int = LINK_LIFETIME_SECONDS) -> str: ...


def dynamodb_resource(settings: Settings):
    """boto3's DynamoDB connection. Empty key settings mean boto3 finds the credentials itself
    (environment variables, ~/.aws/credentials, or the IAM role of the machine)."""
    return boto3.resource("dynamodb", region_name=settings.aws_region,
                          aws_access_key_id=settings.aws_access_key_id or None,
                          aws_secret_access_key=settings.aws_secret_access_key or None)


class DynamoDBStorage:
    """Each file is split into chunks, stored as items of one table:

        object_key  (partition key, string)  the storage key
        chunk       (sort key, number)       0, 1, 2 … in file order
        data        (binary)                 up to CHUNK_BYTES of the file

    The table uses on-demand capacity (see create_table). boto3 is a blocking library, so each
    call runs in a worker thread (asyncio.to_thread).
    """

    def __init__(self, settings: Settings, table=None):
        self.table = table if table is not None else dynamodb_resource(settings).Table(settings.dynamodb_media_table)
        self.links = SignedLinks(settings.secret_key)

    async def put(self, key, data, content_type=None):
        await asyncio.to_thread(self._put, key, data)

    def _put(self, key: str, data: bytes) -> None:
        # batch_writer sends 25 items per request and resends any that DynamoDB couldn't take yet.
        with self.table.batch_writer() as batch:
            for number, start in enumerate(range(0, max(len(data), 1), CHUNK_BYTES)):
                batch.put_item(Item={"object_key": key, "chunk": number, "data": data[start:start + CHUNK_BYTES]})

    async def get(self, key):
        return await asyncio.to_thread(self._get, key)

    def _get(self, key: str) -> bytes:
        chunks = self._chunks(key)
        if not chunks:
            raise FileNotFoundError(key)
        return b"".join(item["data"].value for item in chunks)

    def _chunks(self, key: str, keys_only: bool = False) -> list[dict]:
        """Every chunk of one file, in order. One query returns at most 1 MB, so it pages."""
        request: dict = {"KeyConditionExpression": Key("object_key").eq(key),
                         "ConsistentRead": True}  # a file just written must be complete when read back
        if keys_only:
            request.update(ProjectionExpression="#key, #chunk",
                           ExpressionAttributeNames={"#key": "object_key", "#chunk": "chunk"})
        items: list[dict] = []
        while True:
            page = self.table.query(**request)
            items += page["Items"]
            if "LastEvaluatedKey" not in page:
                return items
            request["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    async def delete(self, key):
        await asyncio.to_thread(self._delete, key)

    def _delete(self, key: str) -> None:
        with self.table.batch_writer() as batch:
            for item in self._chunks(key, keys_only=True):
                batch.delete_item(Key={"object_key": item["object_key"], "chunk": item["chunk"]})

    async def signed_url(self, key, expires=LINK_LIFETIME_SECONDS):
        return self.links.url(key, expires)


class LocalStorage:
    """A folder on this machine: for development and tests."""

    def __init__(self, settings: Settings):
        self.root = Path(settings.local_storage_dir).resolve()
        self.links = SignedLinks(settings.secret_key)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:  # block "../../etc/passwd"-style keys
            raise ValueError("invalid object key")
        return path

    async def put(self, key, data, content_type=None):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key):
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key):
        self._path(key).unlink(missing_ok=True)

    async def signed_url(self, key, expires=LINK_LIFETIME_SECONDS):
        return self.links.url(key, expires)


_storage: Storage | None = None


def get_storage() -> Storage:
    """The configured storage (created on first use)."""
    global _storage
    if _storage is None:
        settings = get_settings()
        backends = {"dynamodb": DynamoDBStorage, "local": LocalStorage}
        _storage = backends[settings.storage_backend](settings)
    return _storage


def object_key(user_id, folder: str, sha256: str, filename: str) -> str:
    extension = PurePosixPath(filename.lower()).suffix[:10]
    return f"{user_id}/{folder}/{sha256}{extension}"


def create_table(settings: Settings, dynamodb=None) -> str:
    """Create the media table unless it exists already. Returns what happened.

    On-demand capacity ("PAY_PER_REQUEST"): the always-free 25 writes/second would need about
    14 seconds per 350 KB chunk. On-demand costs roughly $0.65 per GB uploaded and a few cents
    per GB viewed; the first 25 GB of storage stay free.
    """
    dynamodb = dynamodb or dynamodb_resource(settings)
    name = settings.dynamodb_media_table
    client = dynamodb.meta.client
    try:
        client.describe_table(TableName=name)
        return f"table {name!r} already exists"
    except client.exceptions.ResourceNotFoundException:
        pass
    table = dynamodb.create_table(
        TableName=name,
        KeySchema=[{"AttributeName": "object_key", "KeyType": "HASH"}, {"AttributeName": "chunk", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "object_key", "AttributeType": "S"},
                              {"AttributeName": "chunk", "AttributeType": "N"}],
        BillingMode="PAY_PER_REQUEST")
    table.wait_until_exists()
    return f"created table {name!r} in {settings.aws_region}"


if __name__ == "__main__":
    if sys.argv[1:] != ["create-table"]:
        sys.exit("usage: python -m app.media.storage create-table")
    print(create_table(get_settings()))
