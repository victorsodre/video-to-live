"""JPEG still with Apple MakerNote tag 0x0011 (MakerApple 17)."""

from __future__ import annotations

import struct

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"
APP0 = 0xE0
APP1 = 0xE1
SOS = 0xDA


class StillError(ValueError):
    pass


def _be16(value: int) -> bytes:
    return struct.pack(">H", value)


def _ifd_entry(tag: int, typ: int, count: int, value_or_offset: int) -> bytes:
    return struct.pack(">HHII", tag, typ, count, value_or_offset)


def build_apple_makernote(asset_id: str) -> bytes:
    """Apple iOS\\0\\0\\x01MM + big-endian IFD with tag 0x0011."""
    payload = (asset_id.encode("ascii") + b"\x00")
    # IFD starts at byte 14. One entry (12) + next-IFD (4) = 18, so string at 32.
    string_offset = 32
    header = b"Apple iOS\x00\x00\x01MM"
    ifd = (
        _be16(1)
        + _ifd_entry(0x0011, 2, len(payload), string_offset)
        + struct.pack(">I", 0)
    )
    blob = header + ifd + payload
    if len(header) + len(ifd) != string_offset:
        raise StillError("unexpected Apple MakerNote layout")
    return blob


def build_exif_app1(asset_id: str) -> bytes:
    makernote = build_apple_makernote(asset_id)
    make = b"Apple\x00"

    # TIFF offsets are relative to the TIFF header (start of MM).
    # Layout:
    #   0  TIFF header (8)
    #   8  IFD0: count(2) + 2 entries(24) + next(4) = 30  -> ends 38
    #  38  Make string (6) -> 44
    #  44  ExifIFD: count(2) + 1 entry(12) + next(4) = 18 -> 62
    #  62  MakerNote blob
    ifd0_off = 8
    make_off = 38
    exif_ifd_off = 44
    makernote_off = 62

    ifd0 = (
        _be16(2)
        + _ifd_entry(0x010F, 2, len(make), make_off)  # Make
        + _ifd_entry(0x8769, 4, 1, exif_ifd_off)  # ExifIFD pointer
        + struct.pack(">I", 0)
    )
    if ifd0_off + len(ifd0) != make_off:
        raise StillError("unexpected IFD0 layout")

    exif_ifd = (
        _be16(1)
        + _ifd_entry(0x927C, 7, len(makernote), makernote_off)  # MakerNote
        + struct.pack(">I", 0)
    )
    if make_off + len(make) != exif_ifd_off:
        raise StillError("unexpected Make layout")
    if exif_ifd_off + len(exif_ifd) != makernote_off:
        raise StillError("unexpected ExifIFD layout")

    tiff = (
        b"MM\x00\x2a"
        + struct.pack(">I", ifd0_off)
        + ifd0
        + make
        + exif_ifd
        + makernote
    )
    body = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + _be16(len(body) + 2) + body


def _jpeg_segments(data: bytes) -> list[tuple[int, bytes]]:
    if data[:2] != SOI:
        raise StillError("still image is not JPEG")
    segments: list[tuple[int, bytes]] = []
    offset = 2
    while offset + 2 <= len(data):
        if data[offset] != 0xFF:
            raise StillError("invalid JPEG")
        marker = data[offset + 1]
        if marker == 0xDA:  # SOS: rest of file including entropy + EOI
            segments.append((marker, data[offset:]))
            return segments
        if marker == 0xD9:
            segments.append((marker, data[offset : offset + 2]))
            return segments
        if marker == 0xD8:
            segments.append((marker, data[offset : offset + 2]))
            offset += 2
            continue
        if offset + 4 > len(data):
            raise StillError("truncated JPEG segment")
        length = struct.unpack_from(">H", data, offset + 2)[0]
        end = offset + 2 + length
        if end > len(data):
            raise StillError("JPEG segment extends beyond the file")
        segments.append((marker, data[offset:end]))
        offset = end
    raise StillError("JPEG has no SOS marker")


def stamp_jpeg(jpeg: bytes, asset_id: str) -> bytes:
    """Insert/replace APP1 Exif so MakerApple[17] holds the Live Photo UUID."""
    segments = _jpeg_segments(jpeg)
    app1 = build_exif_app1(asset_id)
    kept: list[bytes] = [SOI]
    inserted = False
    for marker, blob in segments:
        if marker == 0xD8:
            continue
        if marker == APP1 and blob[4:8] == b"Exif":
            continue
        if marker == APP0 and not inserted:
            kept.append(blob)
            kept.append(app1)
            inserted = True
            continue
        if marker == SOS and not inserted:
            kept.append(app1)
            inserted = True
        kept.append(blob)
    if not inserted:
        raise StillError("Exif data does not fit in the JPEG")
    return b"".join(kept)


def read_asset_identifier(data: bytes) -> str | None:
    """Read MakerApple 0x0011 from a JPEG (including JPEG bytes named .HEIC)."""
    if data[:2] != SOI:
        return None
    try:
        segments = _jpeg_segments(data)
    except StillError:
        return None
    for marker, blob in segments:
        if marker != APP1 or blob[4:8] != b"Exif":
            continue
        tiff = blob[10:]
        if tiff[:2] != b"MM":
            continue
        return _read_makernote_uuid(tiff)
    return None


def _read_makernote_uuid(tiff: bytes) -> str | None:
    if len(tiff) < 8:
        return None

    def u16(offset: int) -> int:
        return struct.unpack_from(">H", tiff, offset)[0]

    def u32(offset: int) -> int:
        return struct.unpack_from(">I", tiff, offset)[0]

    def find_tag(ifd: int, tag: int) -> tuple[int, int, int] | None:
        if ifd + 2 > len(tiff):
            return None
        count = u16(ifd)
        for index in range(count):
            entry = ifd + 2 + index * 12
            if entry + 12 > len(tiff):
                return None
            if u16(entry) == tag:
                return u16(entry + 2), u32(entry + 4), u32(entry + 8)
        return None

    ifd0 = u32(4)
    exif = find_tag(ifd0, 0x8769)
    if exif is None:
        return None
    maker = find_tag(exif[2], 0x927C)
    if maker is None:
        return None
    _typ, count, offset = maker
    blob = tiff[offset : offset + count]
    if not blob.startswith(b"Apple iOS\x00"):
        return None
    mn_ifd = 14
    n = struct.unpack_from(">H", blob, mn_ifd)[0]
    for index in range(n):
        entry = mn_ifd + 2 + index * 12
        tag, typ, mn_count, value = struct.unpack_from(">HHII", blob, entry)
        if tag != 0x0011:
            continue
        if mn_count <= 4:
            raw = struct.pack(">I", value)[:mn_count]
        else:
            raw = blob[value : value + mn_count]
        return raw.split(b"\x00", 1)[0].decode("ascii")
    return None
