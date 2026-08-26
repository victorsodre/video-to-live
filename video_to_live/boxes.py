"""Minimal ISO/QuickTime box helpers."""

from __future__ import annotations

import struct
from dataclasses import dataclass


class MovError(ValueError):
    pass


CONTAINER_TYPES = {
    b"moov",
    b"trak",
    b"mdia",
    b"minf",
    b"stbl",
    b"dinf",
    b"edts",
    b"udta",
}


@dataclass(frozen=True)
class Box:
    offset: int
    size: int
    kind: bytes
    header_size: int = 8

    @property
    def payload_offset(self) -> int:
        return self.offset + self.header_size

    @property
    def end(self) -> int:
        return self.offset + self.size


def iter_boxes(data: bytes | bytearray, start: int, end: int) -> tuple[Box, ...]:
    boxes: list[Box] = []
    offset = start
    while offset < end:
        if offset + 8 > end:
            raise MovError("caixa MOV cortada")
        size, kind = struct.unpack_from(">I4s", data, offset)
        header_size = 8
        if size == 1:
            if offset + 16 > end:
                raise MovError("caixa MOV estendida cortada")
            size = struct.unpack_from(">Q", data, offset + 8)[0]
            header_size = 16
        elif size == 0:
            size = end - offset
        if size < header_size or offset + size > end:
            raise MovError(f"tamanho inválido em {kind!r}: {size}")
        boxes.append(Box(offset, size, kind, header_size))
        offset += size
    return tuple(boxes)


def child(data: bytes | bytearray, parent: Box, kind: bytes) -> Box:
    for box in iter_boxes(data, parent.payload_offset, parent.end):
        if box.kind == kind:
            return box
    raise MovError(f"faltou a caixa {kind.decode('latin1')}")


def box(kind: bytes, payload: bytes) -> bytes:
    size = 8 + len(payload)
    if size > 0xFFFFFFFF:
        raise MovError(f"caixa {kind!r} grande demais")
    return struct.pack(">I4s", size, kind) + payload


def full_box(kind: bytes, payload: bytes = b"", *, version: int = 0, flags: int = 0) -> bytes:
    return box(kind, bytes((version,)) + flags.to_bytes(3, "big") + payload)


def walk_boxes(data: bytes | bytearray, start: int, end: int):
    for item in iter_boxes(data, start, end):
        yield item
        if item.kind in CONTAINER_TYPES:
            yield from walk_boxes(data, item.payload_offset, item.end)
        elif item.kind == b"meta":
            # QuickTime moov/meta has no FullBox header; ISO meta does.
            # Walk both: skip 4 bytes only if they look like version/flags.
            payload = data[item.payload_offset : item.end]
            if len(payload) >= 12 and payload[4:8] == b"hdlr":
                yield from walk_boxes(data, item.payload_offset, item.end)
            elif len(payload) >= 8:
                yield from walk_boxes(data, item.payload_offset + 4, item.end)
