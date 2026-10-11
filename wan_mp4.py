"""Detect an audio track in an MP4 without ffmpeg.

The published template is silent video. An audio stream means the graph picked up a
model this image does not ship; MMAudio's checkpoints are CC-BY-NC.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

BOX_HEADER_SIZE = 8
CONTAINER_BOXES = frozenset({b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts"})
HDLR = b"hdlr"
HDLR_TYPE_OFFSET = 8
HDLR_TYPE_SIZE = 4
SOUND_HANDLER = b"soun"
HAS_AUDIO_MESSAGE = "Generated clip still has an audio stream"


def require_no_audio_stream(data: bytes) -> None:
    if mp4_has_sound_stream(data):
        raise ValueError(HAS_AUDIO_MESSAGE)


def mp4_has_sound_stream(data: bytes) -> bool:
    return any(_is_sound_handler(box_type, payload) for box_type, payload in _walk_boxes(data))


def _is_sound_handler(box_type: bytes, payload: bytes) -> bool:
    return box_type == HDLR and _handler_type(payload) == SOUND_HANDLER


def _handler_type(payload: bytes) -> bytes:
    end = HDLR_TYPE_OFFSET + HDLR_TYPE_SIZE
    if len(payload) < end:
        return b""
    return payload[HDLR_TYPE_OFFSET:end]


def _walk_boxes(data: bytes) -> Iterator[tuple[bytes, bytes]]:
    for box_type, payload in _child_boxes(data):
        yield box_type, payload
        yield from _nested_boxes(box_type, payload)


def _nested_boxes(box_type: bytes, payload: bytes) -> Iterator[tuple[bytes, bytes]]:
    if box_type not in CONTAINER_BOXES:
        return
    yield from _walk_boxes(payload)


def _child_boxes(data: bytes) -> Iterator[tuple[bytes, bytes]]:
    offset = 0
    parsed = _read_box(data, offset)
    while parsed is not None:
        box_type, payload, offset = parsed
        yield box_type, payload
        parsed = _read_box(data, offset)


def _read_box(data: bytes, offset: int) -> tuple[bytes, bytes, int] | None:
    if offset + BOX_HEADER_SIZE > len(data):
        return None
    size = int.from_bytes(data[offset : offset + 4], "big")
    if size < BOX_HEADER_SIZE or offset + size > len(data):
        return None
    box_type = data[offset + 4 : offset + BOX_HEADER_SIZE]
    payload = data[offset + BOX_HEADER_SIZE : offset + size]
    return box_type, payload, offset + size
