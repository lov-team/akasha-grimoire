"""Dependency-free QR Code PNG encoder for short UTF-8 URLs.

The implementation intentionally supports the subset Akasha needs: byte mode,
error correction level L, versions 1..10, and mask 0.  It is kept local so a
fresh Skill installation can render the device URL without pip-installing a
package during the credential flow.
"""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path

# Total codewords and L-level ECC layout for QR versions 1..10.
_LAYOUT = {
    1: (26, [(1, 19, 7)]), 2: (44, [(1, 34, 10)]),
    3: (70, [(1, 55, 15)]), 4: (100, [(1, 80, 20)]),
    5: (134, [(1, 108, 26)]), 6: (172, [(2, 68, 18)]),
    7: (196, [(2, 78, 20)]), 8: (242, [(2, 97, 24)]),
    9: (292, [(2, 116, 30)]), 10: (346, [(2, 68, 18), (2, 69, 18)]),
}


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for _ in range(8):
        z = (z << 1) ^ (0x11D if z & 0x80 else 0)
        if y & 0x80:
            z ^= x
        y <<= 1
    return z


def _rs_generator(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 2)
    return result


def _ecc(data: list[int], degree: int) -> list[int]:
    divisor = _rs_generator(degree)
    result = [0] * degree
    for byte in data:
        factor = byte ^ result.pop(0)
        result.append(0)
        for i, coefficient in enumerate(divisor):
            result[i] ^= _gf_mul(coefficient, factor)
    return result


def _bits(value: int, width: int) -> list[int]:
    return [(value >> i) & 1 for i in range(width - 1, -1, -1)]


def _alignment_positions(version: int) -> list[int]:
    if version == 1:
        return []
    count = version // 7 + 2
    step = 26 if version == 32 else ((version * 4 + count * 2 + 1) // (count * 2 - 2)) * 2
    return [6] + [version * 4 + 10 - i * step for i in range(count - 1)][::-1]


def _finder(modules: list[list[bool]], used: list[list[bool]], x: int, y: int) -> None:
    size = len(modules)
    for dy in range(-1, 8):
        for dx in range(-1, 8):
            xx, yy = x + dx, y + dy
            if 0 <= xx < size and 0 <= yy < size:
                modules[yy][xx] = 0 <= dx <= 6 and 0 <= dy <= 6 and (dx in {0, 6} or dy in {0, 6} or (2 <= dx <= 4 and 2 <= dy <= 4))
                used[yy][xx] = True


def _make_matrix(version: int, codewords: list[int]) -> list[list[bool]]:
    size = version * 4 + 17
    modules = [[False] * size for _ in range(size)]
    used = [[False] * size for _ in range(size)]
    _finder(modules, used, 0, 0)
    _finder(modules, used, size - 7, 0)
    _finder(modules, used, 0, size - 7)
    for i in range(8, size - 8):
        modules[6][i] = modules[i][6] = i % 2 == 0
        used[6][i] = used[i][6] = True
    positions = _alignment_positions(version)
    for cy in positions:
        for cx in positions:
            if used[cy][cx]:
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    modules[cy + dy][cx + dx] = max(abs(dx), abs(dy)) != 1
                    used[cy + dy][cx + dx] = True
    # Reserve and write format bits for level L / mask 0 (0x77C4).
    fmt = [(0x77C4 >> i) & 1 for i in range(15)]
    a = [(i, 8) for i in range(0, 6)] + [(7, 8), (8, 8), (8, 7)] + [(8, i) for i in range(5, -1, -1)]
    b = [(size - 1 - i, 8) for i in range(8)] + [(8, size - 7 + i) for i in range(7)]
    for bit, (x, y) in zip(fmt, a): modules[y][x] = bool(bit); used[y][x] = True
    for bit, (x, y) in zip(fmt, b): modules[y][x] = bool(bit); used[y][x] = True
    modules[size - 8][8] = True
    used[size - 8][8] = True
    data_bits = [bit for byte in codewords for bit in _bits(byte, 8)]
    index = 0
    right = size - 1
    upward = True
    while right >= 1:
        if right == 6: right -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for y in rows:
            for x in (right, right - 1):
                if used[y][x]: continue
                bit = data_bits[index] if index < len(data_bits) else 0
                index += 1
                modules[y][x] = bool(bit ^ ((x + y) % 2 == 0))
        upward = not upward
        right -= 2
    return modules


def encode_matrix(text: str) -> list[list[bool]]:
    payload = text.encode("utf-8")
    version = next((v for v, (_, groups) in _LAYOUT.items() if len(payload) + 2 <= sum(n * data for n, data, _ in groups)), None)
    if version is None:
        raise ValueError("QR payload is too long")
    _, groups = _LAYOUT[version]
    data_capacity = sum(n * data for n, data, _ in groups)
    stream = _bits(0b0100, 4) + _bits(len(payload), 8 if version <= 9 else 16)
    for byte in payload: stream += _bits(byte, 8)
    stream += [0] * min(4, data_capacity * 8 - len(stream))
    stream += [0] * ((8 - len(stream) % 8) % 8)
    data = [sum(stream[i + j] << (7 - j) for j in range(8)) for i in range(0, len(stream), 8)]
    for pad in (0xEC, 0x11) * data_capacity:
        if len(data) >= data_capacity: break
        data.append(pad)
    blocks, offset = [], 0
    for count, data_len, ecc_len in groups:
        for _ in range(count):
            chunk = data[offset:offset + data_len]; offset += data_len
            blocks.append((chunk, _ecc(chunk, ecc_len)))
    codewords: list[int] = []
    for i in range(max(len(block[0]) for block in blocks)):
        codewords += [block[0][i] for block in blocks if i < len(block[0])]
    for i in range(max(len(block[1]) for block in blocks)):
        codewords += [block[1][i] for block in blocks if i < len(block[1])]
    return _make_matrix(version, codewords)


def write_png(text: str, path: str | Path, *, scale: int = 8, border: int = 4) -> Path:
    matrix = encode_matrix(text)
    width = (len(matrix) + border * 2) * scale
    rows = bytearray()
    for y in range(width):
        rows.append(0)
        my = y // scale - border
        for x in range(width):
            mx = x // scale - border
            dark = 0 <= my < len(matrix) and 0 <= mx < len(matrix) and matrix[my][mx]
            rows.append(0 if dark else 255)
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, width, 8, 0, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        stream = os.fdopen(fd, "wb")
        fd = -1
        with stream:
            stream.write(png)
            stream.flush()
    finally:
        if fd >= 0:
            os.close(fd)
    return target
