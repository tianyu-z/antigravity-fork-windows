"""Create a separate, verified Fork patch for Antigravity 2.35.2 arm64.

This script does not install or sign the output and never changes its input.
"""
import hashlib
import io
import struct
import sys
import zipfile
import zlib
from pathlib import Path


EXPECTED_SHA256 = "8b11ecde9d089ebbe4511871e75bd046e04f33865c27b617e29a3c237a2bd575"
ARCHIVE_START = 159091037
ARCHIVE_END = 165254803
CHANGES = (
    (b"conversationForkingEnabled:!1", b"conversationForkingEnabled:!0"),
    (b"conversationForkingHistoricalStep:!1", b"conversationForkingHistoricalStep:!0"),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def patched_binary(source):
    if digest(source) != EXPECTED_SHA256:
        raise ValueError("Input is not the verified Antigravity 2.35.2 arm64 language server.")
    archive_start, archive_end = ARCHIVE_START, ARCHIVE_END
    original_archive = source[archive_start:archive_end]
    archive = bytearray(original_archive)
    with zipfile.ZipFile(io.BytesIO(original_archive)) as z:
        if z.testzip() is not None:
            raise ValueError("Original resource ZIP failed its CRC check.")
        infos = z.infolist()
        if len({i.filename for i in infos}) != len(infos):
            raise ValueError("Duplicate ZIP entry names.")
        resources = {i.filename: digest(z.read(i)) for i in infos}
        info = z.getinfo("main.js")
        if info.compress_type != zipfile.ZIP_DEFLATED or info.flag_bits & 8:
            raise ValueError("Unsupported main.js compression or ZIP layout.")
        changed = z.read(info)
        for before, after in CHANGES:
            if len(before) != len(after) or changed.count(before) != 1:
                raise ValueError("Expected Fork default is not unique.")
            changed = changed.replace(before, after)

    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    compressed = compressor.compress(changed) + compressor.flush()
    if len(compressed) > info.compress_size:
        raise ValueError("Patched main.js exceeds its original ZIP allocation.")
    local = info.header_offset
    if archive[local:local + 4] != b"PK\x03\x04":
        raise ValueError("Invalid ZIP local header.")
    name_length, extra_length = struct.unpack_from("<HH", archive, local + 26)
    content = local + 30 + name_length + extra_length
    archive[content:content + info.compress_size] = compressed + b"\0" * (info.compress_size - len(compressed))
    crc = zlib.crc32(changed)
    struct.pack_into("<I", archive, local + 14, crc)

    eocd = archive.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise ValueError("Missing ZIP end record.")
    central_size, central = struct.unpack_from("<II", archive, eocd + 12)
    central_end = central + central_size
    matches = 0
    while central < central_end:
        if archive[central:central + 4] != b"PK\x01\x02":
            raise ValueError("Invalid ZIP central directory.")
        name_len, extra_len, comment_len = struct.unpack_from("<HHH", archive, central + 28)
        if archive[central + 46:central + 46 + name_len] == b"main.js":
            struct.pack_into("<I", archive, central + 16, crc)
            matches += 1
        central += 46 + name_len + extra_len + comment_len
    if matches != 1 or central != central_end or len(archive) != len(original_archive):
        raise ValueError("ZIP directory or allocation changed unexpectedly.")

    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if z.testzip() is not None or z.read("main.js") != changed:
            raise ValueError("Patched resource ZIP failed verification.")
        if z.namelist() != [i.filename for i in infos]:
            raise ValueError("ZIP resource inventory changed.")
        for name, expected in resources.items():
            if name != "main.js" and digest(z.read(name)) != expected:
                raise ValueError("An unrelated resource changed: " + name)

    result = source[:archive_start] + bytes(archive) + source[archive_end:]
    if len(result) != len(source):
        raise ValueError("Executable size changed before signing.")
    return result


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python3 patch_antigravity_macos.py ORIGINAL_SERVER NEW_OUTPUT_SERVER")
    source, output = map(Path, sys.argv[1:])
    if output.exists():
        raise SystemExit("Output already exists; refusing to overwrite it.")
    patched = patched_binary(source.read_bytes())
    with output.open("xb") as f:
        f.write(patched)
    output.chmod(source.stat().st_mode & 0o777)
    print("Created:", output)
    print("SHA-256 before signing:", digest(patched))


if __name__ == "__main__":
    main()
