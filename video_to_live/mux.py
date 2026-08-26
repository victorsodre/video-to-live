"""Inject Live Photo movie metadata and the two Core Media mebx tracks.

ffmpeg cannot copy mebx (the tag becomes stts). All metadata is written at
the box/atom level here.
"""

from __future__ import annotations

import struct
import time
from collections.abc import Sequence
from pathlib import Path

from video_to_live.boxes import Box, MovError, box, child, full_box, iter_boxes, walk_boxes
from video_to_live.constants import (
    CONTENT_IDENTIFIER_KEY,
    FRAME_COUNT,
    INFO_EMPTY_EDIT,
    INFO_MEDIA_DURATION,
    INFO_SAMPLE_COUNT,
    INFO_SAMPLE_DELTA,
    INFO_SAMPLES_PER_CHUNK,
    INFO_TIMESCALE,
    LIVE_PHOTO_AUTO_KEY,
    LIVE_PHOTO_INFO_KEY,
    LIVE_PHOTO_INFO_SAMPLE,
    MVHD_DURATION,
    STILL_EMPTY_EDIT,
    STILL_IMAGE_SAMPLE,
    STILL_IMAGE_TIME_KEY,
    STILL_IMAGE_TRANSFORM_KEY,
    STILL_MEDIA_DURATION,
    TIMESCALE,
    VIDEO_MDHD_DURATION,
    VIDEO_STTS,
)

QUICKTIME_EPOCH_OFFSET = 2_082_844_800
LANGUAGE_UNDETERMINED = 0x55C4


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


def _track_id(data: bytes | bytearray, track: Box) -> int:
    tkhd = child(data, track, b"tkhd")
    version = data[tkhd.payload_offset]
    offset = tkhd.offset + (20 if version == 0 else 28)
    return struct.unpack_from(">I", data, offset)[0]


def _stsz_count(data: bytes | bytearray, stbl: Box) -> int:
    stsz = child(data, stbl, b"stsz")
    return struct.unpack_from(">I", data, stsz.payload_offset + 8)[0]


def _media_handler(subtype: bytes, name: bytes) -> bytes:
    return full_box(
        b"hdlr",
        b"mhlr" + subtype + b"appl" + struct.pack(">II", 0, 0) + _pascal(name),
    )


def _data_handler() -> bytes:
    return full_box(
        b"hdlr",
        b"dhlralisappl" + struct.pack(">II", 0, 0) + _pascal(b"Core Media Data Handler"),
    )


def _patched_mvhd(data: bytes, mvhd: Box, duration: int, next_track_id: int) -> bytes:
    blob = bytearray(data[mvhd.offset : mvhd.end])
    if blob[8] != 0:
        raise MovError("mvhd v1 não suportado")
    struct.pack_into(">I", blob, 20, TIMESCALE)
    struct.pack_into(">I", blob, 24, duration)
    struct.pack_into(">I", blob, len(blob) - 4, next_track_id)
    return bytes(blob)


def _patched_tkhd(data: bytes, tkhd: Box, duration: int, flags: int = 0x0F) -> bytes:
    blob = bytearray(data[tkhd.offset : tkhd.end])
    if blob[8] != 0:
        raise MovError("tkhd v1 não suportado")
    blob[9:12] = flags.to_bytes(3, "big")
    struct.pack_into(">I", blob, 28, duration)
    return bytes(blob)


def _patched_mdhd(data: bytes, mdhd: Box, duration: int, timescale: int | None = None) -> bytes:
    blob = bytearray(data[mdhd.offset : mdhd.end])
    if blob[8] != 0:
        raise MovError("mdhd v1 não suportado")
    if timescale is not None:
        struct.pack_into(">I", blob, 20, timescale)
    struct.pack_into(">I", blob, 24, duration)
    struct.pack_into(">H", blob, 28, LANGUAGE_UNDETERMINED)
    return bytes(blob)


def _video_stts() -> bytes:
    payload = struct.pack(">I", len(VIDEO_STTS))
    for count, delta in VIDEO_STTS:
        payload += struct.pack(">II", count, delta)
    return full_box(b"stts", payload)


def _patch_video_track(data: bytes, trak: Box) -> bytes:
    tkhd = child(data, trak, b"tkhd")
    mdia = child(data, trak, b"mdia")
    mdhd = child(data, mdia, b"mdhd")
    minf = child(data, mdia, b"minf")
    stbl = child(data, minf, b"stbl")
    sample_count = _stsz_count(data, stbl)
    if sample_count != FRAME_COUNT:
        raise MovError(f"esperado {FRAME_COUNT} quadros, veio {sample_count}")

    new_stbl = box(
        b"stbl",
        b"".join(
            _video_stts() if item.kind == b"stts" else data[item.offset : item.end]
            for item in iter_boxes(data, stbl.payload_offset, stbl.end)
        ),
    )
    new_minf = box(
        b"minf",
        b"".join(
            new_stbl
            if item.kind == b"stbl"
            else _data_handler()
            if item.kind == b"hdlr"
            else data[item.offset : item.end]
            for item in iter_boxes(data, minf.payload_offset, minf.end)
        ),
    )
    new_mdia = box(
        b"mdia",
        _patched_mdhd(data, mdhd, VIDEO_MDHD_DURATION, TIMESCALE)
        + _media_handler(b"vide", b"Core Media Video")
        + new_minf,
    )
    parts = []
    for item in iter_boxes(data, trak.payload_offset, trak.end):
        if item.kind == b"tkhd":
            parts.append(_patched_tkhd(data, tkhd, MVHD_DURATION))
        elif item.kind == b"edts":
            continue
        elif item.kind == b"mdia":
            parts.append(new_mdia)
        else:
            parts.append(data[item.offset : item.end])
    return box(b"trak", b"".join(parts))


def _mebx_key_entry(local_id: int, key: bytes, dtyp_payload: bytes) -> bytes:
    keyd = struct.pack(">I4s4s", 12 + len(key), b"keyd", b"mdta") + key
    dtyp = box(b"dtyp", dtyp_payload)
    return struct.pack(">II", 8 + len(keyd) + len(dtyp), local_id) + keyd + dtyp


def _mebx_keys(entries: list[tuple[int, bytes, bytes]]) -> bytes:
    return box(b"keys", b"".join(_mebx_key_entry(local_id, key, dtyp) for local_id, key, dtyp in entries))


def _core_media_track(
    *,
    track_id: int,
    media_timescale: int,
    media_duration: int,
    empty_edit: int,
    media_edit_duration: int,
    keys: list[tuple[int, bytes, bytes]],
    sample_size: int,
    sample_count: int,
    sample_delta: int,
    chunk_offsets: list[int],
    samples_per_chunk: Sequence[tuple[int, int]],
) -> bytes:
    timestamp = _now()
    if any(offset > 0xFFFFFFFF for offset in chunk_offsets):
        raise MovError("offset mebx passa de 32 bits")
    track_duration = empty_edit + media_edit_duration
    elst = full_box(
        b"elst",
        struct.pack(">I", 2)
        + struct.pack(">IiHH", empty_edit, -1, 1, 0)
        + struct.pack(">IiHH", media_edit_duration, 0, 1, 0),
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
    mdhd = full_box(
        b"mdhd",
        struct.pack(
            ">IIIIHH",
            timestamp,
            timestamp,
            media_timescale,
            media_duration,
            LANGUAGE_UNDETERMINED,
            0,
        ),
    )
    gmin = full_box(b"gmin", struct.pack(">HHHHhH", 0x40, 0x8000, 0x8000, 0x8000, 0, 0))
    alias = full_box(b"alis", flags=1)
    dref = full_box(b"dref", struct.pack(">I", 1) + alias)
    mebx = box(b"mebx", b"\0" * 6 + struct.pack(">H", 1) + _mebx_keys(keys))
    stsd = full_box(b"stsd", struct.pack(">I", 1) + mebx)
    stts = full_box(b"stts", struct.pack(">III", 1, sample_count, sample_delta))
    stsc_payload = struct.pack(">I", len(samples_per_chunk))
    for first_chunk, count in samples_per_chunk:
        stsc_payload += struct.pack(">III", first_chunk, count, 1)
    stsc = full_box(b"stsc", stsc_payload)
    stsz = full_box(b"stsz", struct.pack(">II", sample_size, sample_count))
    stco = full_box(
        b"stco",
        struct.pack(">I", len(chunk_offsets)) + b"".join(struct.pack(">I", offset) for offset in chunk_offsets),
    )
    stbl = box(b"stbl", stsd + stts + stsc + stsz + stco)
    minf = box(b"minf", box(b"gmhd", gmin) + _data_handler() + box(b"dinf", dref) + stbl)
    mdia = box(b"mdia", mdhd + _media_handler(b"meta", b"Core Media Metadata") + minf)
    return box(b"trak", tkhd + box(b"edts", elst) + mdia)


def _info_track(track_id: int, chunk_offsets: list[int]) -> bytes:
    return _core_media_track(
        track_id=track_id,
        media_timescale=INFO_TIMESCALE,
        media_duration=INFO_MEDIA_DURATION,
        empty_edit=INFO_EMPTY_EDIT,
        media_edit_duration=TIMESCALE,  # 1.0 s at 600 Hz
        keys=[(1, LIVE_PHOTO_INFO_KEY.encode("ascii"), struct.pack(">II", 0, 0))],
        sample_size=len(LIVE_PHOTO_INFO_SAMPLE),
        sample_count=INFO_SAMPLE_COUNT,
        sample_delta=INFO_SAMPLE_DELTA,
        chunk_offsets=chunk_offsets,
        samples_per_chunk=((1, INFO_SAMPLES_PER_CHUNK), (2, INFO_SAMPLES_PER_CHUNK)),
    )


def _still_track(track_id: int, chunk_offset: int) -> bytes:
    return _core_media_track(
        track_id=track_id,
        media_timescale=TIMESCALE,
        media_duration=STILL_MEDIA_DURATION,
        empty_edit=STILL_EMPTY_EDIT,
        media_edit_duration=STILL_MEDIA_DURATION,
        keys=[
            (1, STILL_IMAGE_TIME_KEY.encode("ascii"), struct.pack(">II", 0, 0x41)),
            (2, STILL_IMAGE_TRANSFORM_KEY.encode("ascii"), struct.pack(">II", 0, 0x53)),
        ],
        sample_size=len(STILL_IMAGE_SAMPLE),
        sample_count=1,
        sample_delta=STILL_MEDIA_DURATION,
        chunk_offsets=[chunk_offset],
        samples_per_chunk=((1, 1),),
    )


def _movie_metadata(content_identifier: str) -> bytes:
    identifier = content_identifier.encode("ascii")
    if not identifier or b"\0" in identifier:
        raise MovError("content identifier vazio")
    handler = box(b"hdlr", b"\0" * 8 + b"mdta" + b"\0" * 14)
    keys = full_box(
        b"keys",
        struct.pack(">I", 2)
        + box(b"mdta", CONTENT_IDENTIFIER_KEY.encode("ascii"))
        + box(b"mdta", LIVE_PHOTO_AUTO_KEY.encode("ascii")),
    )
    items = box(
        b"ilst",
        box(struct.pack(">I", 1), box(b"data", struct.pack(">II", 1, 0) + identifier))
        + box(struct.pack(">I", 2), box(b"data", struct.pack(">II", 0x15, 0) + b"\x01")),
    )
    return box(b"meta", handler + keys + items)


def _rewrite_ftyp() -> bytes:
    return box(b"ftyp", b"qt  " + struct.pack(">I", 0) + b"qt  ")


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


def inject_live_photo_metadata(source: Path, destination: Path, content_identifier: str) -> None:
    original = source.read_bytes()
    top = iter_boxes(original, 0, len(original))
    moov = next((item for item in top if item.kind == b"moov"), None)
    mdat = next((item for item in top if item.kind == b"mdat"), None)
    if moov is None or mdat is None:
        raise MovError("MOV sem moov/mdat")
    if moov.header_size != 8 or mdat.header_size != 8:
        raise MovError("caixa de tamanho estendido não suportada")
    if _movie_timescale(original, moov) != TIMESCALE:
        raise MovError(f"timescale do filme deve ser {TIMESCALE}")

    payload = original[mdat.payload_offset : mdat.end]
    children = iter_boxes(original, moov.payload_offset, moov.end)
    track_ids = [_track_id(original, item) for item in children if item.kind == b"trak"]
    next_id = max(track_ids, default=0) + 1

    info_payload = LIVE_PHOTO_INFO_SAMPLE * INFO_SAMPLE_COUNT
    chunk_stride = INFO_SAMPLES_PER_CHUNK * len(LIVE_PHOTO_INFO_SAMPLE)

    def tracks(info_off: int, still_off: int) -> bytes:
        return _info_track(next_id, [info_off, info_off + chunk_stride]) + _still_track(next_id + 1, still_off)

    meta = _movie_metadata(content_identifier)
    kept = bytearray()
    for item in children:
        if item.kind in {b"udta", b"meta", b"free"}:
            continue
        if item.kind == b"mvhd":
            kept.extend(_patched_mvhd(original, item, MVHD_DURATION, next_id + 2))
            continue
        if item.kind == b"trak":
            kept.extend(_patch_video_track(original, item))
            continue
        kept.extend(original[item.offset : item.end])

    new_ftyp = _rewrite_ftyp()
    draft_moov = box(b"moov", bytes(kept) + tracks(0, 0) + meta)
    new_mdat_payload_offset = len(new_ftyp) + len(draft_moov) + 8
    info_off = new_mdat_payload_offset + len(payload)
    still_off = info_off + len(info_payload)
    final_tracks = tracks(info_off, still_off)

    patched = bytearray(bytes(kept) + final_tracks + meta)
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

    new_mdat = box(b"mdat", payload + info_payload + STILL_IMAGE_SAMPLE)
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
        data_box = next(
            (child_box for child_box in iter_boxes(data, item.payload_offset, item.end) if child_box.kind == b"data"),
            None,
        )
        if data_box is None:
            continue
        out[names[index - 1]] = bytes(data[data_box.payload_offset + 8 : data_box.end])
    return out


def read_mvhd(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    moov = next((item for item in iter_boxes(data, 0, len(data)) if item.kind == b"moov"), None)
    if moov is None:
        raise MovError("MOV sem moov")
    mvhd = child(data, moov, b"mvhd")
    version = data[mvhd.payload_offset]
    timescale_off = mvhd.offset + (20 if version == 0 else 28)
    duration_off = mvhd.offset + (24 if version == 0 else 36)
    timescale = struct.unpack_from(">I", data, timescale_off)[0]
    duration = int(struct.unpack_from(">I" if version == 0 else ">Q", data, duration_off)[0])
    return timescale, duration


def _stts_entries(data: bytes | bytearray, stts: Box) -> list[tuple[int, int]]:
    count = struct.unpack_from(">I", data, stts.payload_offset + 4)[0]
    entries = []
    for index in range(count):
        entries.append(struct.unpack_from(">II", data, stts.payload_offset + 8 + index * 8))
    return entries


def _stsc_entries(data: bytes | bytearray, stsc: Box) -> list[tuple[int, int, int]]:
    count = struct.unpack_from(">I", data, stsc.payload_offset + 4)[0]
    entries = []
    for index in range(count):
        entries.append(struct.unpack_from(">III", data, stsc.payload_offset + 8 + index * 12))
    return entries


def _elst_entries(data: bytes | bytearray, trak: Box) -> list[tuple[int, int]]:
    try:
        edts = child(data, trak, b"edts")
        elst = child(data, edts, b"elst")
    except MovError:
        return []
    version = data[elst.payload_offset]
    count = struct.unpack_from(">I", data, elst.payload_offset + 4)[0]
    offset = elst.payload_offset + 8
    entries: list[tuple[int, int]] = []
    for _ in range(count):
        if version == 0:
            duration, media_time = struct.unpack_from(">Ii", data, offset)
            offset += 12
        else:
            duration, media_time = struct.unpack_from(">Qq", data, offset)
            offset += 20
        entries.append((duration, media_time))
    return entries


def _first_sample(data: bytes, stbl: Box) -> bytes:
    stsz = child(data, stbl, b"stsz")
    default_size, count = struct.unpack_from(">II", data, stsz.payload_offset + 4)
    if count < 1:
        return b""
    size = default_size if default_size else struct.unpack_from(">I", data, stsz.payload_offset + 12)[0]
    try:
        offsets = child(data, stbl, b"stco")
        first = struct.unpack_from(">I", data, offsets.payload_offset + 8)[0]
    except MovError:
        offsets = child(data, stbl, b"co64")
        first = struct.unpack_from(">Q", data, offsets.payload_offset + 8)[0]
    return bytes(data[first : first + size])


def describe_video_track(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    moov = next((item for item in iter_boxes(data, 0, len(data)) if item.kind == b"moov"), None)
    if moov is None:
        raise MovError("MOV sem moov")
    for trak in iter_boxes(data, moov.payload_offset, moov.end):
        if trak.kind != b"trak":
            continue
        mdia = child(data, trak, b"mdia")
        hdlr = child(data, mdia, b"hdlr")
        subtype = data[hdlr.payload_offset + 8 : hdlr.payload_offset + 12]
        if subtype != b"vide":
            continue
        mdhd = child(data, mdia, b"mdhd")
        minf = child(data, mdia, b"minf")
        stbl = child(data, minf, b"stbl")
        stts = child(data, stbl, b"stts")
        manufacturer = data[hdlr.payload_offset + 12 : hdlr.payload_offset + 16]
        name_blob = data[hdlr.payload_offset + 24 : hdlr.end]
        name = name_blob[1 : 1 + name_blob[0]].decode("latin1") if name_blob else ""
        language = struct.unpack_from(">H", data, mdhd.payload_offset + 20)[0]
        duration = struct.unpack_from(">I", data, mdhd.payload_offset + 16)[0]
        tkhd = child(data, trak, b"tkhd")
        flags = int.from_bytes(data[tkhd.payload_offset + 1 : tkhd.payload_offset + 4], "big")
        return {
            "hdlr_type": data[hdlr.payload_offset + 4 : hdlr.payload_offset + 8],
            "subtype": subtype,
            "manufacturer": manufacturer,
            "name": name,
            "mdhd_duration": duration,
            "language": language,
            "stts": _stts_entries(data, stts),
            "tkhd_flags": flags,
        }
    raise MovError("MOV sem trilha de vídeo")


def describe_mebx(path: Path) -> list[dict[str, object]]:
    data = path.read_bytes()
    known = (LIVE_PHOTO_INFO_KEY, STILL_IMAGE_TIME_KEY)
    found: list[dict[str, object]] = []
    for item in walk_boxes(data, 0, len(data)):
        if item.kind != b"trak":
            continue
        blob = data[item.offset : item.end]
        if b"mebx" not in blob:
            continue
        keys = [key for key in known if key.encode("ascii") in blob]
        if not keys:
            continue
        mdia = child(data, item, b"mdia")
        minf = child(data, mdia, b"minf")
        stbl = child(data, minf, b"stbl")
        stsz = child(data, stbl, b"stsz")
        stts = child(data, stbl, b"stts")
        stsc = child(data, stbl, b"stsc")
        mdhd = child(data, mdia, b"mdhd")
        default_size, count = struct.unpack_from(">II", data, stsz.payload_offset + 4)
        timescale = struct.unpack_from(">I", data, mdhd.payload_offset + 12)[0]
        duration = struct.unpack_from(">I", data, mdhd.payload_offset + 16)[0]
        elst = _elst_entries(data, item)
        found.append(
            {
                "keys": keys,
                "samples": count,
                "sample_size": default_size,
                "stts": _stts_entries(data, stts),
                "stsc": _stsc_entries(data, stsc),
                "timescale": timescale,
                "duration": duration,
                "empty_edit": elst[0][0] if elst and elst[0][1] == -1 else 0,
                "first_sample": _first_sample(data, stbl),
            }
        )
    return found


def mebx_keys(path: Path) -> list[str]:
    names: list[str] = []
    for track in describe_mebx(path):
        for key in track["keys"]:
            if key not in names:
                names.append(key)  # type: ignore[arg-type]
    return names
