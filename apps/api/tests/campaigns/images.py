# ruff: noqa: E501  (SQL and picture bytes)
"""Pictures a test can upload: well formed PNG, JPEG and WebP files built by hand (the pixels are
nonsense, the structure is real), with the metadata a phone leaves in them."""

import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
GPS = b"GPSLatitude=-23.5505 GPSLongitude=-46.6333 Make=Acme Model=Phone"


def png_chunk(kind: bytes, body: bytes = b"") -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def make_png(
    width: int = 2,
    height: int = 2,
    *,
    extra: tuple[tuple[bytes, bytes], ...] = ((b"tEXt", b"Comment\x00" + GPS), (b"eXIf", GPS)),
    trailing: bytes = b"",
) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00" * ((width * 3 + 1) * height))
    chunks = [
        png_chunk(b"IHDR", header),
        png_chunk(b"gAMA", struct.pack(">I", 45455)),
        *(png_chunk(kind, body) for kind, body in extra),
        png_chunk(b"IDAT", pixels),
        png_chunk(b"IEND"),
    ]
    return PNG_SIGNATURE + b"".join(chunks) + trailing


def jpeg_segment(marker: int, body: bytes) -> bytes:
    return b"\xff" + bytes([marker]) + struct.pack(">H", len(body) + 2) + body


SCAN = b"\x12\x34\xff\x00\x56\xff\xd3\x78\x9a"  # entropy data: a stuffed 0xFF and a restart marker


def make_jpeg(width: int = 4, height: int = 4, *, trailing: bytes = b"") -> bytes:
    return b"".join(
        [
            b"\xff\xd8",
            jpeg_segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"),
            jpeg_segment(0xE1, b"Exif\x00\x00" + GPS),
            jpeg_segment(
                0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta>" + GPS + b"</x:xmpmeta>"
            ),
            jpeg_segment(0xE2, b"ICC_PROFILE\x00\x01\x01profile-bytes"),
            jpeg_segment(0xE2, b"MPF\x00second picture with " + GPS),
            jpeg_segment(0xED, b"Photoshop 3.0\x00" + GPS),
            jpeg_segment(0xFE, b"taken with a phone"),
            jpeg_segment(0xDB, b"\x00" + bytes(64)),
            jpeg_segment(0xC0, b"\x08" + struct.pack(">HH", height, width) + b"\x01\x01\x11\x00"),
            jpeg_segment(0xC4, b"\x00" + bytes(16)),
            jpeg_segment(0xDA, b"\x01\x01\x00\x00\x3f\x00"),
            SCAN,
            b"\xff\xd9",
            trailing,
        ]
    )


def riff_chunk(kind: bytes, body: bytes) -> bytes:
    return kind + struct.pack("<I", len(body)) + body + (b"\x00" if len(body) & 1 else b"")


def make_webp(width: int = 8, height: int = 8, *, trailing: bytes = b"") -> bytes:
    flags = 0x20 | 0x10 | 0x08 | 0x04  # colour profile, alpha, EXIF and XMP
    canvas = (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    lossless = (
        b"\x2f" + ((width - 1) | ((height - 1) << 14)).to_bytes(4, "little") + b"\x00\x00\x00"
    )
    body = b"".join(
        [
            riff_chunk(b"VP8X", bytes([flags]) + b"\x00\x00\x00" + canvas),
            riff_chunk(b"ICCP", b"profile-bytes"),
            riff_chunk(b"VP8L", lossless),
            riff_chunk(b"EXIF", b"Exif\x00\x00" + GPS),
            riff_chunk(b"XMP ", b"<x:xmpmeta>" + GPS + b"</x:xmpmeta>"),
        ]
    )
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body + trailing
