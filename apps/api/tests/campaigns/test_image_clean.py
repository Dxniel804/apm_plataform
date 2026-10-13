# ruff: noqa: E501  (SQL and picture bytes)
"""The pictures of a campaign are public: the metadata of a phone photo must not reach the world,
and a file that is not a well formed picture must not either."""

import struct

import pytest

from app.storage.image_clean import MAX_SIDE, ImageRejected, clean_image
from tests.campaigns.images import (
    GPS,
    PNG_SIGNATURE,
    SCAN,
    make_jpeg,
    make_png,
    make_webp,
    png_chunk,
)

SECRETS = (b"GPS", b"Exif", b"xmpmeta", b"Acme", b"Photoshop", b"taken with a phone", b"MPF")


def _no_metadata(data: bytes) -> None:
    for secret in SECRETS:
        assert secret not in data, secret


# --- PNG ------------------------------------------------------------------------------------------


def test_png_loses_its_text_exif_and_what_follows_the_end() -> None:
    cleaned = clean_image("image/png", make_png(trailing=b"hidden payload " + GPS))

    _no_metadata(cleaned)
    assert b"hidden payload" not in cleaned
    assert cleaned.startswith(PNG_SIGNATURE) and cleaned.endswith(png_chunk(b"IEND"))
    assert b"gAMA" in cleaned and b"IDAT" in cleaned  # what draws it stays


def test_png_cleaning_twice_changes_nothing_more() -> None:
    once = clean_image("image/png", make_png())
    assert clean_image("image/png", once) == once


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not a picture at all",
        PNG_SIGNATURE,  # no chunks
        PNG_SIGNATURE + png_chunk(b"IEND"),  # no header first
        make_png()[:-10],  # truncated
        make_png()[:40] + b"\x00" + make_png()[41:],  # a flipped byte: the CRC refuses it
        PNG_SIGNATURE + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)),  # no end
        make_png(extra=((b"ABCD", b"an unknown CRITICAL chunk"),)),
    ],
)
def test_a_broken_png_is_refused(data: bytes) -> None:
    with pytest.raises(ImageRejected) as refusal:
        clean_image("image/png", data)
    assert str(refusal.value) == "image_malformed"


@pytest.mark.parametrize("size", [(MAX_SIDE + 1, 10), (10, MAX_SIDE + 1), (0, 10), (7000, 7000)])
def test_a_picture_too_big_in_pixels_is_refused(size: tuple[int, int]) -> None:
    # The header says the size; the pixels are never decoded, so the file itself can be tiny.
    header = png_chunk(b"IHDR", struct.pack(">IIBBBBB", *size, 8, 2, 0, 0, 0))
    data = PNG_SIGNATURE + header + png_chunk(b"IDAT", b"x") + png_chunk(b"IEND")
    with pytest.raises(ImageRejected) as refusal:
        clean_image("image/png", data)
    assert str(refusal.value) == "image_dimensions"


# --- JPEG -----------------------------------------------------------------------------------------


def test_jpeg_loses_exif_xmp_comments_extra_pictures_and_the_trailer() -> None:
    cleaned = clean_image("image/jpeg", make_jpeg(trailing=b"hidden payload " + GPS))

    _no_metadata(cleaned)
    assert b"hidden payload" not in cleaned
    assert cleaned.startswith(b"\xff\xd8\xff\xe0") and cleaned.endswith(b"\xff\xd9")
    assert b"JFIF" in cleaned and b"ICC_PROFILE" in cleaned  # the header and the colours stay
    assert SCAN in cleaned  # the entropy data is copied untouched, stuffed bytes and restarts too


def test_jpeg_cleaning_twice_changes_nothing_more() -> None:
    once = clean_image("image/jpeg", make_jpeg())
    assert clean_image("image/jpeg", once) == once


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\xff\xd8",
        b"\xff\xd8\xff\xd9",  # no size, no scan
        b"\xff\xd8garbage",
        make_jpeg()[:-2],  # no end of image
        make_jpeg()[:30],  # cut in the middle of a segment
    ],
)
def test_a_broken_jpeg_is_refused(data: bytes) -> None:
    with pytest.raises(ImageRejected):
        clean_image("image/jpeg", data)


def test_a_huge_jpeg_is_refused_by_its_header() -> None:
    with pytest.raises(ImageRejected) as refusal:
        clean_image("image/jpeg", make_jpeg(MAX_SIDE + 1, 10))
    assert str(refusal.value) == "image_dimensions"


# --- WebP -----------------------------------------------------------------------------------------


def test_webp_loses_exif_and_xmp_and_says_so_in_its_header() -> None:
    cleaned = clean_image("image/webp", make_webp(trailing=b"hidden payload " + GPS))

    _no_metadata(cleaned)
    assert b"hidden payload" not in cleaned
    assert cleaned[:4] == b"RIFF" and cleaned[8:12] == b"WEBP"
    assert struct.unpack("<I", cleaned[4:8])[0] == len(cleaned) - 8  # the size is rewritten
    assert b"EXIF" not in cleaned and b"XMP " not in cleaned
    flags = cleaned[20]  # the first byte of the VP8X chunk
    assert flags & 0x0C == 0  # no EXIF, no XMP
    assert flags & 0x30 == 0x30  # the colour profile and the alpha stay
    assert b"ICCP" in cleaned and b"VP8L" in cleaned


def test_webp_cleaning_twice_changes_nothing_more() -> None:
    once = clean_image("image/webp", make_webp())
    assert clean_image("image/webp", once) == once


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"RIFF",
        b"RIFF\x04\x00\x00\x00WEBP",  # no picture in it
        make_webp()[:-8],  # shorter than the RIFF header says
        b"RIFX" + make_webp()[4:],
    ],
)
def test_a_broken_webp_is_refused(data: bytes) -> None:
    with pytest.raises(ImageRejected):
        clean_image("image/webp", data)


def test_a_huge_webp_is_refused_by_its_header() -> None:
    with pytest.raises(ImageRejected) as refusal:
        clean_image("image/webp", make_webp(MAX_SIDE + 1, 10))
    assert str(refusal.value) == "image_dimensions"


# --- the rest -------------------------------------------------------------------------------------


@pytest.mark.parametrize("content_type", ["application/pdf", "image/gif", "text/html", ""])
def test_any_other_type_is_refused(content_type: str) -> None:
    with pytest.raises(ImageRejected) as refusal:
        clean_image(content_type, make_png())
    assert str(refusal.value) == "image_type"


def test_the_refusal_never_quotes_the_file() -> None:
    with pytest.raises(ImageRejected) as refusal:
        clean_image("image/png", b"secret-token-in-the-file")
    assert "secret" not in str(refusal.value)
