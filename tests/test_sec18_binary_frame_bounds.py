"""Binary-frame bounds-check regression (SEC-18)."""

import struct

import numpy as np
import pytest

from juniper_cascor_worker.constants import (
    BINARY_FRAME_DTYPE_ENCODING,
    BINARY_FRAME_HEADER_LENGTH_BYTES,
    BINARY_FRAME_HEADER_LENGTH_FORMAT,
)
from juniper_cascor_worker.worker import (
    BINARY_FRAME_MAX_DTYPE_LEN,
    BINARY_FRAME_MAX_NDIM,
    BINARY_FRAME_MAX_TOTAL_ELEMENTS,
    BinaryFrameProtocolError,
    _decode_binary_frame,
    _encode_binary_frame,
)


def _header(ndim: int, shape: tuple[int, ...], dtype_str: bytes) -> bytes:
    header = struct.pack(BINARY_FRAME_HEADER_LENGTH_FORMAT, ndim)
    header += struct.pack(f"<{len(shape)}I", *shape)
    header += struct.pack(BINARY_FRAME_HEADER_LENGTH_FORMAT, len(dtype_str))
    header += dtype_str
    return header


class TestBinaryFrameRoundTrip:
    def test_roundtrip_small_matrix(self) -> None:
        arr = np.arange(12, dtype=np.float32).reshape(3, 4)
        decoded = _decode_binary_frame(_encode_binary_frame(arr))
        assert decoded.shape == arr.shape
        assert decoded.dtype == arr.dtype
        np.testing.assert_array_equal(decoded, arr)

    def test_roundtrip_vector(self) -> None:
        arr = np.arange(6, dtype=np.int64)
        decoded = _decode_binary_frame(_encode_binary_frame(arr))
        np.testing.assert_array_equal(decoded, arr)


class TestBinaryFrameBoundsRejection:
    def test_rejects_excessive_ndim(self) -> None:
        frame = _header(BINARY_FRAME_MAX_NDIM + 1, (0,) * (BINARY_FRAME_MAX_NDIM + 1), b"float32")
        with pytest.raises(BinaryFrameProtocolError, match="ndim="):
            _decode_binary_frame(frame)

    def test_rejects_oversized_total_elements(self) -> None:
        # Force total_elements to overflow the cap via two large dims.
        bad = BINARY_FRAME_MAX_TOTAL_ELEMENTS + 1
        dims = (bad, 1)
        frame = _header(len(dims), dims, b"float32")
        frame += np.zeros(1, dtype=np.float32).tobytes()
        with pytest.raises(BinaryFrameProtocolError, match="total_elements"):
            _decode_binary_frame(frame)

    def test_rejects_oversized_dtype_len(self) -> None:
        # Hand-build a frame with an impossibly long dtype descriptor.
        ndim = 1
        shape = (1,)
        long_dtype = b"f" * (BINARY_FRAME_MAX_DTYPE_LEN + 1)
        header = struct.pack(BINARY_FRAME_HEADER_LENGTH_FORMAT, ndim)
        header += struct.pack(f"<{ndim}I", *shape)
        header += struct.pack(BINARY_FRAME_HEADER_LENGTH_FORMAT, len(long_dtype))
        header += long_dtype
        with pytest.raises(BinaryFrameProtocolError, match="dtype_len"):
            _decode_binary_frame(header)

    def test_accepts_boundary_ndim(self) -> None:
        shape = (1,) * BINARY_FRAME_MAX_NDIM
        dtype_bytes = str(np.dtype("float32")).encode(BINARY_FRAME_DTYPE_ENCODING)
        frame = _header(BINARY_FRAME_MAX_NDIM, shape, dtype_bytes)
        frame += np.zeros(1, dtype=np.float32).tobytes()
        decoded = _decode_binary_frame(frame)
        assert decoded.shape == shape
