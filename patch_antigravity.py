"""Build and verify a version-pinned Antigravity UI patch.

The actual installation is changed separately, only after the patched binary
has been tested. This script never edits the source executable.
"""
import hashlib
import io
import struct
import sys
import zipfile
import zlib
from pathlib import Path


EXPECTED_SHA256 = 'fcdf7454007c6edc8162e601628c28cc1e6f575be849f329bb864c41ba6e6b02'
ARCHIVE_START = 182614461
ARCHIVE_END = 188778227
CHANGES = (
    (b'conversationForkingEnabled:!1', b'conversationForkingEnabled:!0'),
    (b'conversationForkingHistoricalStep:!1', b'conversationForkingHistoricalStep:!0'),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def patched_binary(source):
    if digest(source) != EXPECTED_SHA256:
        raise ValueError('Installed binary differs from the verified 2.35.2 build; refusing to patch.')
    data = bytearray(source)
    original_archive = bytes(data[ARCHIVE_START:ARCHIVE_END])
    archive = bytearray(original_archive)
    with zipfile.ZipFile(io.BytesIO(original_archive)) as z:
        if z.testzip() is not None:
            raise ValueError('Original resource archive failed its CRC check.')
        info = z.getinfo('main.js')
        original = z.read(info)
        if info.compress_type != zipfile.ZIP_DEFLATED or info.flag_bits & 8:
            raise ValueError('Unexpected archive layout.')
        changed = original
        for before, after in CHANGES:
            if len(before) != len(after) or changed.count(before) != 1:
                raise ValueError('Expected UI flag pattern was not unique.')
            changed = changed.replace(before, after)

    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    compressed = compressor.compress(changed) + compressor.flush()
    if len(compressed) > info.compress_size:
        raise ValueError('Patched script does not fit in the original archive entry.')
    local = info.header_offset
    if archive[local:local + 4] != b'PK\x03\x04':
        raise ValueError('Invalid ZIP local header.')
    name_length, extra_length = struct.unpack_from('<HH', archive, local + 26)
    content = local + 30 + name_length + extra_length
    end = content + info.compress_size
    archive[content:end] = compressed + b'\0' * (info.compress_size - len(compressed))
    crc = zlib.crc32(changed)
    struct.pack_into('<I', archive, local + 14, crc)

    eocd = archive.rfind(b'PK\x05\x06')
    if eocd < 0:
        raise ValueError('Missing ZIP end record.')
    central_size, central = struct.unpack_from('<II', archive, eocd + 12)
    central_end = central + central_size
    matches = 0
    while central < central_end:
        if archive[central:central + 4] != b'PK\x01\x02':
            raise ValueError('Invalid ZIP central directory.')
        name_len, extra_len, comment_len = struct.unpack_from('<HHH', archive, central + 28)
        name = archive[central + 46:central + 46 + name_len]
        if name == b'main.js':
            struct.pack_into('<I', archive, central + 16, crc)
            matches += 1
        central += 46 + name_len + extra_len + comment_len
    if matches != 1 or central != central_end:
        raise ValueError('Unexpected main.js central directory entries.')
    if len(archive) != len(original_archive):
        raise ValueError('Archive size changed.')
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if z.testzip() is not None or z.read('main.js') != changed:
            raise ValueError('Patched archive verification failed.')

    data[ARCHIVE_START:ARCHIVE_END] = archive
    if len(data) != len(source):
        raise ValueError('Executable size changed.')
    return data


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python patch_antigravity.py SOURCE_EXE NEW_OUTPUT_EXE')
    source, output = map(Path, sys.argv[1:])
    if output.exists():
        raise SystemExit('Output already exists; refusing to overwrite it.')
    patched = patched_binary(source.read_bytes())
    with output.open('xb') as target:
        target.write(patched)
    print('Created verified patched copy:', output)
    print('SHA-256:', digest(patched))


if __name__ == '__main__':
    main()
