"""What every route that takes a file shares: the size is bounded BEFORE the body is read and again
while it is streamed, the sha256 is computed on the way to the store, a failed write leaves nothing
behind, and a client-supplied file name is only ever a clean label.

Used by the receipts of an expense and by the photos of a staff request.
"""

import logging
import unicodedata
from collections.abc import Iterator
from typing import BinaryIO, Protocol

from fastapi import Request

from app.core.errors import ProblemError
from app.storage.base import CHUNK_SIZE, AttachmentStore

logger = logging.getLogger(__name__)

# Room for the multipart envelope (boundaries, headers, the other fields) around the file.
MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_DECLARED_DIGITS = 15
FILE_NAME_LENGTH = 200


class TooLarge(Exception):
    """The file is bigger than the limit (raised while it is streamed)."""


def check_declared_length(request: Request, max_bytes: int) -> None:
    """The request must declare its size, and the size must fit before anything is read."""
    declared = request.headers.get("content-length", "")
    # ASCII digits only: str.isdigit() is also true for "²" or Arabic-Indic digits, which int()
    # refuses. A number of more than 15 digits is far over any limit (and int() of thousands of
    # digits is refused too).
    if not (declared.isascii() and declared.isdigit()):
        raise ProblemError(411, "length_required", "The request must declare its size")
    if len(declared) > MAX_DECLARED_DIGITS or int(declared) > max_bytes + MULTIPART_OVERHEAD_BYTES:
        raise ProblemError(413, "payload_too_large", "The file is larger than the limit")


def clean_file_name(raw: str | None, extension: str) -> str:
    """A display name from what the client called the file: no path, no control characters, a
    bounded length. It is only a label (the file lives under a key made by the server)."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = name.encode("utf-8", "ignore").decode("utf-8")  # drops a lone surrogate
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip()
    name = name[:FILE_NAME_LENGTH].strip(" .")
    return name or f"anexo{extension}"


class Hasher(Protocol):
    def update(self, data: bytes, /) -> None: ...


def limited_chunks(first: bytes, stream: BinaryIO, hasher: Hasher, limit: int) -> Iterator[bytes]:
    total = 0
    chunk = first
    while chunk:
        total += len(chunk)
        if total > limit:
            raise TooLarge
        hasher.update(chunk)
        yield chunk
        chunk = stream.read(CHUNK_SIZE)


def discard(store: AttachmentStore, key: str) -> None:
    """Remove a file that no row will point to. It runs while another error is being raised, so it
    must never raise itself (it would replace the error the caller needs to see): a failure is
    logged, with the class of the error and never the key or a path, and the file is left behind."""
    try:
        store.delete(key)
    except Exception as error:
        logger.error(
            "could not remove an attachment file after a failed write",
            extra={"error_class": type(error).__name__},
        )
