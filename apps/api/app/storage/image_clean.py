"""Remove the metadata of a picture the management uploads, before the whole world can see it.

The cover and the products of a campaign are PUBLIC once the campaign is on sale, and a photo from a
phone carries where and when it was taken (GPS, the model of the device, sometimes a thumbnail of
the original, a name). This module rewrites the container of PNG, JPEG and WebP keeping only what
the picture needs to be drawn (the pixels, the colour profile, the transparency, the animation) and
drops everything else: EXIF, XMP, comments, text chunks, timestamps, the extra images of a
multi-picture JPEG and whatever was appended after the end of the file.

It never decodes the pixels (no image library, so no decoder to attack): it walks the structure
of the file, checks it is well formed, reads the size of the picture from its header and refuses
what is not valid or is too big. A file it cannot read is refused, never passed through.
"""

import struct
import zlib


class ImageRejected(ValueError):
    """The file is not a well formed PNG, JPEG or WebP, or its picture is too big. The message is
    a fixed code: nothing of the file ever appears in it."""


MAX_SIDE = 8000  # pixels, each side
MAX_PIXELS = 40_000_000

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# What a PNG needs to be drawn; every other chunk (text, EXIF, timestamps, private ones) goes.
_PNG_KEEP = frozenset(
    {
        b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT",
        b"bKGD", b"pHYs", b"acTL", b"fcTL", b"fdAT",
    }
)  # fmt: skip

# JPEG markers that stand alone (no length): TEM, the restart markers, SOI and EOI.
_JPEG_STANDALONE = frozenset({0x01, 0xD8, 0xD9, *range(0xD0, 0xD8)})
_JPEG_SOF = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)

_WEBP_KEEP = frozenset({b"VP8 ", b"VP8L", b"VP8X", b"ANIM", b"ANMF", b"ALPH", b"ICCP"})
_VP8X_EXIF_AND_XMP = 0x08 | 0x04


def _check_size(width: int, height: int) -> None:
    if width < 1 or height < 1 or width > MAX_SIDE or height > MAX_SIDE:
        raise ImageRejected("image_dimensions")
    if width * height > MAX_PIXELS:
        raise ImageRejected("image_dimensions")


def _malformed() -> ImageRejected:
    return ImageRejected("image_malformed")


# --- PNG ------------------------------------------------------------------------------------------


def _clean_png(data: bytes) -> bytes:
    if not data.startswith(_PNG_SIGNATURE):
        raise _malformed()
    out = bytearray(_PNG_SIGNATURE)
    position = len(_PNG_SIGNATURE)
    first = True
    seen_data = False
    while position + 12 <= len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        kind = data[position + 4 : position + 8]
        end = position + 12 + length
        if length > 0x7FFFFFFF or end > len(data):
            raise _malformed()
        body = data[position + 8 : position + 8 + length]
        (crc,) = struct.unpack(">I", data[end - 4 : end])
        if zlib.crc32(kind + body) != crc:
            raise _malformed()
        if first:
            if kind != b"IHDR" or length != 13:
                raise _malformed()
            width, height = struct.unpack(">II", body[:8])
            _check_size(width, height)
            first = False
        # An unknown CRITICAL chunk (upper case first letter) means a file we cannot vouch for.
        if kind not in _PNG_KEEP and kind[:1].isupper():
            raise _malformed()
        if kind == b"IDAT":
            seen_data = True
        if kind in _PNG_KEEP:
            out += data[position:end]
        position = end
        if kind == b"IEND":
            if not seen_data:
                raise _malformed()
            return bytes(out)  # whatever follows IEND is dropped
    raise _malformed()


# --- JPEG -----------------------------------------------------------------------------------------


def _keep_jpeg_segment(marker: int, body: bytes) -> bool:
    if marker == 0xE0:  # APP0: the JFIF header yes, the JFXX thumbnails no
        return body.startswith(b"JFIF\x00")
    if marker == 0xE2:  # APP2: the colour profile yes, the multi-picture index (MPF) no
        return body.startswith(b"ICC_PROFILE\x00")
    if marker == 0xEE:  # APP14: how Adobe says the colours are stored
        return body.startswith(b"Adobe")
    # APP1 (EXIF, XMP), APP3 to APP13, APP15 and the comments (0xFE) all go.
    return not (0xE1 <= marker <= 0xEF or marker == 0xFE)


def _clean_jpeg(data: bytes) -> bytes:
    if not data.startswith(b"\xff\xd8"):
        raise _malformed()
    out = bytearray(b"\xff\xd8")
    position = 2
    size_seen = False
    scan_seen = False
    while position < len(data):
        if data[position] != 0xFF:
            raise _malformed()
        while position < len(data) and data[position] == 0xFF:  # fill bytes before a marker
            position += 1
        if position >= len(data):
            raise _malformed()
        marker = data[position]
        position += 1
        if marker == 0xD9:  # EOI: whatever follows is dropped
            if not (size_seen and scan_seen):
                raise _malformed()
            out += b"\xff\xd9"
            return bytes(out)
        if marker in _JPEG_STANDALONE or marker == 0x00:
            raise _malformed()
        if position + 2 > len(data):
            raise _malformed()
        (length,) = struct.unpack(">H", data[position : position + 2])
        end = position + length
        if length < 2 or end > len(data):
            raise _malformed()
        body = data[position + 2 : end]
        if marker in _JPEG_SOF:
            if len(body) < 6:
                raise _malformed()
            height, width = struct.unpack(">HH", body[1:5])
            _check_size(width, height)
            size_seen = True
        if _keep_jpeg_segment(marker, body):
            out += b"\xff" + bytes([marker]) + data[position:end]
        position = end
        if marker == 0xDA:  # SOS: the entropy-coded data runs to the next real marker
            scan_seen = True
            start = position
            while position + 1 < len(data):
                if data[position] == 0xFF and data[position + 1] not in (0x00, *range(0xD0, 0xD8)):
                    if data[position + 1] == 0xFF:
                        position += 1  # a fill byte: look at the next one
                        continue
                    break
                position += 1
            else:
                raise _malformed()
            out += data[start:position]
    raise _malformed()


# --- WebP -----------------------------------------------------------------------------------------


def _webp_dimensions(kind: bytes, body: bytes) -> tuple[int, int] | None:
    if kind == b"VP8X" and len(body) >= 10:
        return (
            1 + int.from_bytes(body[4:7], "little"),
            1 + int.from_bytes(body[7:10], "little"),
        )
    if kind == b"VP8 " and len(body) >= 10 and body[3:6] == b"\x9d\x01\x2a":
        return (
            int.from_bytes(body[6:8], "little") & 0x3FFF,
            int.from_bytes(body[8:10], "little") & 0x3FFF,
        )
    if kind == b"VP8L" and len(body) >= 5 and body[0] == 0x2F:
        bits = int.from_bytes(body[1:5], "little")
        return (1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF))
    return None


def _clean_webp(data: bytes) -> bytes:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise _malformed()
    (declared,) = struct.unpack("<I", data[4:8])
    if declared + 8 > len(data) or declared < 4:
        raise _malformed()
    stop = declared + 8  # whatever follows the RIFF container is dropped
    position = 12
    chunks = bytearray()
    sized = False
    drawable = False
    while position + 8 <= stop:
        kind = data[position : position + 4]
        (length,) = struct.unpack("<I", data[position + 4 : position + 8])
        end = position + 8 + length + (length & 1)
        if end > stop:
            raise _malformed()
        body = data[position + 8 : position + 8 + length]
        if kind in _WEBP_KEEP:
            found = _webp_dimensions(kind, body)
            if found is not None:
                _check_size(*found)
                sized = True
            if kind in (b"VP8 ", b"VP8L", b"ANMF"):
                drawable = True
            if kind == b"VP8X":
                if length < 10:
                    raise _malformed()
                body = bytes([body[0] & ~_VP8X_EXIF_AND_XMP & 0xFF]) + body[1:]
            chunks += (
                kind + struct.pack("<I", len(body)) + body + (b"\x00" if len(body) & 1 else b"")
            )
        position = end
    if position != stop or not (sized and drawable):
        raise _malformed()
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WEBP" + bytes(chunks)


_CLEANERS = {"image/png": _clean_png, "image/jpeg": _clean_jpeg, "image/webp": _clean_webp}


def clean_image(content_type: str, data: bytes) -> bytes:
    """The same picture without metadata. Raises `ImageRejected` (a fixed code) when the file is
    not a well formed picture of the given type, or when it is too big in pixels."""
    cleaner = _CLEANERS.get(content_type)
    if cleaner is None:
        raise ImageRejected("image_type")
    return cleaner(data)
