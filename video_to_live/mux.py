"""Inject Live Photo movie metadata and the two Core Media mebx tracks."""

from __future__ import annotations

import struct
import time
from pathlib import Path

from video_to_live.boxes import Box, MovError, box, child, full_box, iter_boxes, walk_boxes
from video_to_live.constants import (
    CONTENT_IDENTIFIER_KEY,
    LIVE_PHOTO_AUTO_KEY,
    STILL_IMAGE_TIME_KEY,
    STILL_MARKER_TICKS,
    STILL_TIME_SECONDS,
    TIMESCALE,
    VIDEO_ORIENTATION_KEY,
    VITALITY_SCORE_KEY,
    VITALITY_VERSION_KEY,
)

QUICKTIME_EPOCH_OFFSET = 2_082_844_800

# Boxed metadata samples (size + local id + value).
STILL_IMAGE_SAMPLE = b"\x00\x00\x00\x09\x00\x00\x00\x01\xff"
# SInt16 1 = top-left; the clip is already 1080x1920 portrait.
ORIENTATION_SAMPLE = b"\x00\x00\x00\x0a\x00\x00\x00\x01\x00\x01"


def _pascal(text: bytes) -> bytes:
    if len(text) > 255:
        raise MovError("nome Pascal grande demais")
    return bytes((len(text),)) + text


def _now() -> int:
    return int(time.time()) + QUICKTIME_EPOCH_OFFSET


def _matrix() -> bytes:
    return struct.pack(">9i", 0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000)


def _movie_timescale(data: bytes | bytearray, moov: Box) -> int:
    mvhd = child(data, moov, b"mvhd")
    version = data[mvhd.payload_offset]
    offset = mvhd.offset + (20 if version == 0 else 28)
    timescale = struct.unpack_from(">I", data, offset)[0]
    if timescale <= 0:
        raise MovError("timescale do filme inválido")
    return timescale


def _movie_duration(data: bytes | bytearray, moov: Box) -> int:
    mvhd = child(data, moov, b"mvhd")
    version = data[mvhd.payload_offset]
    offset = mvhd.offset + (24 if version == 0 else 36)
    fmt = ">I" if version == 0 else ">Q"
    return int(struct.unpack_from(fmt, data, offset)[0])


def _track_id(data: bytes | bytearray, track: Box) -> int:
    tkhd = child(data, track, b"tkhd")
    version = data[tkhd.payload_offset]
    offset = tkhd.offset + (20 if version == 0 else 28)
    return struct.unpack_from(">I", data, offset)[0]


def _mebx_keys(key: bytes, dtyp: int) -> bytes:
    key_description = struct.pack(">I4s4s", 12 + len(key), b"keyd", b"mdta") + key
    data_type = box(b"dtyp", struct.pack(">II", 0, dtyp))
    payload_size = 8 + len(key_description) + len(data_type)
    return box(b"keys", struct.pack(">II", payload_size, 1) + key_description + data_type)


def _core_media_track(
    *,
    track_id: int,
    movie_timescale: int,
    movie_duration: int,
    media_duration: int,
    sample: bytes,
    key: bytes,
    dtyp: int,
    chunk_offset: int,
    empty_edit: int = 0,
) -> bytes:
    timestamp = _now()
    if chunk_offset > 0xFFFFFFFF:
        raise MovError("offset mebx passa de 32 bits")
    marker_duration = max(1, round(media_duration * movie_timescale / TIMESCALE))
    if empty_edit:
        track_duration = empty_edit + marker_duration
        elst = full_box(
            b"elst",
            struct.pack(">I", 2)
            + struct.pack(">IiHH", empty_edit, -1, 1, 0)
            + struct.pack(">IiHH", marker_duration, 0, 1, 0),
        )
    else:
        track_duration = movie_duration
        elst = full_box(
            b"elst",
            struct.pack(">I", 1) + struct.pack(">IiHH", movie_duration, 0, 1, 0),
        )
    tkhd = full_box(
        b"tkhd",
        struct.pack(">IIIII", timestamp, timestamp, track_id, 0, track_duration)
        + b"\0" * 8
        + struct.pack(">hhhh", 0, 0, 0, 0)
        + _matrix()
        + struct.pack(">II", 0, 0),
        flags=0x0F,
    )
    edts = box(b"edts", elst)
    mdhd = full_box(
        b"mdhd",
        struct.pack(">IIIIHH", timestamp, timestamp, TIMESCALE, media_duration, 0x55C4, 0),
    )
    media_handler = full_box(
        b"hdlr",
        b"mhlrmetaappl" + struct.pack(">II", 1, 0) + _pascal(b"Core Media Metadata"),
    )
    gmin = full_box(b"gmin", struct.pack(">HHHHhH", 0x40, 0x8000, 0x8000, 0x8000, 0, 0))
    gmhd = box(b"gmhd", gmin)
    data_handler = full_box(
        b"hdlr",
        b"dhlralisappl" + struct.pack(">II", 0, 0) + _pascal(b"Core Media Data Handler"),
    )
    alias = full_box(b"alis", flags=1)
    dref = full_box(b"dref", struct.pack(">I", 1) + alias)
    dinf = box(b"dinf", dref)
    mebx = box(b"mebx", b"\0" * 6 + struct.pack(">H", 1) + _mebx_keys(key, dtyp))
    stsd = full_box(b"stsd", struct.pack(">I", 1) + mebx)
    stts = full_box(b"stts", struct.pack(">III", 1, 1, media_duration))
    stsc = full_box(b"stsc", struct.pack(">IIII", 1, 1, 1, 1))
    stsz = full_box(b"stsz", struct.pack(">II", len(sample), 1))
    stco = full_box(b"stco", struct.pack(">II", 1, chunk_offset))
    stbl = box(b"stbl", stsd + stts + stsc + stsz + stco)
    minf = box(b"minf", gmhd + data_handler + dinf + stbl)
    mdia = box(b"mdia", mdhd + media_handler + minf)
    return box(b"trak", tkhd + edts + mdia)


def _movie_metadata(content_identifier: str) -> bytes:
    identifier = content_identifier.encode("ascii")
    if not identifier or b"\0" in identifier:
        raise MovError("content identifier vazio")
    handler = box(b"hdlr", b"\0" * 8 + b"mdta" + b"\0" * 14)
    keys = full_box(
        b"keys",
        struct.pack(">I", 4)
        + box(b"mdta", CONTENT_IDENTIFIER_KEY.encode("ascii"))
        + box(b"mdta", LIVE_PHOTO_AUTO_KEY.encode("ascii"))
        + box(b"mdta", VITALITY_SCORE_KEY.encode("ascii"))
        + box(b"mdta", VITALITY_VERSION_KEY.encode("ascii")),
    )
    items = box(
        b"ilst",
        box(struct.pack(">I", 1), box(b"data", struct.pack(">II", 1, 0) + identifier))
        + box(struct.pack(">I", 2), box(b"data", struct.pack(">II", 0x15, 0) + b"\x01"))
        + box(struct.pack(">I", 3), box(b"data", struct.pack(">II", 0x17, 0) + struct.pack(">f", 1.0)))
        + box(struct.pack(">I", 4), box(b"data", struct.pack(">II", 0x15, 0) + struct.pack(">i", 4))),
    )
    return box(b"meta", handler + keys + items)


def _rewrite_ftyp() -> bytes:
    payload = b"qt  " + struct.pack(">I", 0) + b"qt  "
    return box(b"ftyp", payload)


def _relocated_chunk_offsets(
    data: bytearray,
    start: int,
    end: int,
    old_payload_offset: int,
    new_payload_offset: int,
    payload_size: int,
) -> None:
    for item in iter_boxes(data, start, end):
        if item.kind in {b"stco", b"co64"}:
            count = struct.unpack_from(">I", data, item.offset + 12)[0]
            width = 4 if item.kind == b"stco" else 8
            fmt = ">I" if width == 4 else ">Q"
            for index in range(count):
                pos = item.offset + 16 + index * width
                value = struct.unpack_from(fmt, data, pos)[0]
                relative = value - old_payload_offset
                if relative < 0 or relative >= payload_size:
                    continue
                new_value = new_payload_offset + relative
                if width == 4 and new_value > 0xFFFFFFFF:
                    raise MovError("stco passou de 32 bits")
                struct.pack_into(fmt, data, pos, new_value)
        elif item.kind in {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"dinf", b"udta"}:
            _relocated_chunk_offsets(
                data,
                item.payload_offset,
                item.end,
                old_payload_offset,
                new_payload_offset,
                payload_size,
            )


def _set_next_track_id(data: bytearray, next_track_id: int) -> None:
    local_moov = Box(0, len(data), b"moov", header_size=0)
    mvhd = child(data, local_moov, b"mvhd")
    struct.pack_into(">I", data, mvhd.end - 4, next_track_id)


def inject_live_photo_metadata(source: Path, destination: Path, content_identifier: str) -> None:
    original = source.read_bytes()
    top = iter_boxes(original, 0, len(original))
    ftyp = next((item for item in top if item.kind == b"ftyp"), None)
    moov = next((item for item in top if item.kind == b"moov"), None)
    mdat = next((item for item in top if item.kind == b"mdat"), None)
    if ftyp is None or moov is None or mdat is None:
        raise MovError("MOV sem ftyp/moov/mdat")
    if original[ftyp.payload_offset : ftyp.payload_offset + 4] not in {b"qt  ", b"isom", b"mp41", b"mp42"}:
        # ffmpeg -brand qt writes qt  ; tolerate a slip and force qt on rewrite.
        pass
    if moov.header_size != 8 or mdat.header_size != 8:
        raise MovError("caixa de tamanho estendido não suportada")

    payload = original[mdat.payload_offset : mdat.end]
    movie_timescale = _movie_timescale(original, moov)
    movie_duration = _movie_duration(original, moov)
    children = iter_boxes(original, moov.payload_offset, moov.end)
    track_ids = [_track_id(original, item) for item in children if item.kind == b"trak"]
    next_id = max(track_ids, default=0) + 1
    empty_edit = max(0, round(STILL_TIME_SECONDS * movie_timescale))

    def tracks(orientation_off: int, still_off: int) -> bytes:
        orientation = _core_media_track(
            track_id=next_id,
            movie_timescale=movie_timescale,
            movie_duration=movie_duration,
            media_duration=max(STILL_MARKER_TICKS, round(movie_duration * TIMESCALE / movie_timescale)),
            sample=ORIENTATION_SAMPLE,
            key=VIDEO_ORIENTATION_KEY.encode("ascii"),
            dtyp=0x42,
            chunk_offset=orientation_off,
        )
        still = _core_media_track(
            track_id=next_id + 1,
            movie_timescale=movie_timescale,
            movie_duration=movie_duration,
            media_duration=STILL_MARKER_TICKS,
            sample=STILL_IMAGE_SAMPLE,
            key=STILL_IMAGE_TIME_KEY.encode("ascii"),
            dtyp=0x41,
            chunk_offset=still_off,
            empty_edit=empty_edit,
        )
        return orientation + still

    meta = _movie_metadata(content_identifier)
    placeholder = tracks(0, 0)
    kept = bytearray()
    for item in children:
        if item.kind in {b"udta", b"meta"}:
            continue
        kept.extend(original[item.offset : item.end])

    # First pass: size the new moov (stco values are fixed-width).
    new_ftyp = _rewrite_ftyp()
    draft_payload = bytes(kept) + placeholder + meta
    draft_moov = box(b"moov", draft_payload)
    new_mdat_payload_offset = len(new_ftyp) + len(draft_moov) + 8
    orientation_off = new_mdat_payload_offset + len(payload)
    still_off = orientation_off + len(ORIENTATION_SAMPLE)
    final_tracks = tracks(orientation_off, still_off)

    patched = bytearray(bytes(kept) + final_tracks + meta)
    _set_next_track_id(patched, next_id + 2)
    _relocated_chunk_offsets(
        patched,
        0,
        len(kept),
        mdat.payload_offset,
        new_mdat_payload_offset,
        len(payload),
    )
    new_moov = box(b"moov", bytes(patched))
    if len(new_ftyp) + len(new_moov) + 8 != new_mdat_payload_offset:
        raise MovError("layout moov/mdat inconsistente")

    new_mdat_payload = payload + ORIENTATION_SAMPLE + STILL_IMAGE_SAMPLE
    new_mdat = box(b"mdat", new_mdat_payload)
    destination.write_bytes(new_ftyp + new_moov + new_mdat)


def read_quicktime_keys(path: Path) -> dict[str, bytes]:
    data = path.read_bytes()
    moov = next((item for item in iter_boxes(data, 0, len(data)) if item.kind == b"moov"), None)
    if moov is None:
        return {}
    meta = next((item for item in iter_boxes(data, moov.payload_offset, moov.end) if item.kind == b"meta"), None)
    if meta is None:
        return {}
    keys_box = next((item for item in iter_boxes(data, meta.payload_offset, meta.end) if item.kind == b"keys"), None)
    ilst = next((item for item in iter_boxes(data, meta.payload_offset, meta.end) if item.kind == b"ilst"), None)
    if keys_box is None or ilst is None:
        return {}
    names: list[str] = []
    offset = keys_box.payload_offset + 8
    while offset + 8 <= keys_box.end:
        size = struct.unpack_from(">I", data, offset)[0]
        if size < 8 or offset + size > keys_box.end:
            break
        names.append(data[offset + 8 : offset + size].decode("ascii", "replace"))
        offset += size
    out: dict[str, bytes] = {}
    for item in iter_boxes(data, ilst.payload_offset, ilst.end):
        index = struct.unpack_from(">I", data, item.offset + 4)[0]
        if not 1 <= index <= len(names):
            continue
        data_box = next((child_box for child_box in iter_boxes(data, item.payload_offset, item.end) if child_box.kind == b"data"), None)
        if data_box is None:
            continue
        out[names[index - 1]] = bytes(data[data_box.payload_offset + 8 : data_box.end])
    return out


def mebx_keys(path: Path) -> list[str]:
    data = path.read_bytes()
    found: list[str] = []
    for item in walk_boxes(data, 0, len(data)):
        if item.kind != b"trak":
            continue
        blob = data[item.offset : item.end]
        if b"mebx" not in blob:
            continue
        for key in (STILL_IMAGE_TIME_KEY, VIDEO_ORIENTATION_KEY):
            if key.encode("ascii") in blob and key not in found:
                found.append(key)
    return found
