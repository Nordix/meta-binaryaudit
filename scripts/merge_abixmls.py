#!/usr/bin/env python3
# Copyright (C) 2026 Ericsson Software Technology AB
# SPDX-License-Identifier: GPL-2.0-only
#
# Merge multiple per-arch abixmls.tar.zst archives (one per CI arch build)
# into a single archive that abi_compare.py can consume transparently.
#
# Usage — explicit files:
#   python3 merge_abixmls.py \
#       --input  distro-1.0-cortexa53-abixmls.tar.zst \
#                distro-1.0-x86_64-abixmls.tar.zst \
#       --output distro-1.0-all-abixmls.tar.zst
#
# Usage — directory (all *abixmls*.tar.zst found recursively):
#   python3 merge_abixmls.py \
#       --input  /path/to/build/repos/ \
#       --output distro-1.0-all-abixmls.tar.zst
#
# Usage — mix of files and directories:
#   python3 merge_abixmls.py \
#       --input  /builds/repo1 /builds/repo2/specific.tar.zst \
#       --output distro-1.0-all-abixmls.tar.zst
#
# The merged archive preserves the full
#   packages/<pkg_arch>/<pkg>/binaryaudit/abixml/<pkg_arch>/
# directory structure so that abi_compare.py needs no changes.

import argparse
import io
import os
import sys
import tarfile
import tempfile
from pathlib import Path


def _open_zst_tar(path, mode):
    """Open a .tar.zst file for reading or writing via the zstandard module."""
    try:
        import zstandard
    except ImportError:
        sys.exit("error: 'zstandard' Python package is required (pip install zstandard)")
    zst_ctx = zstandard.ZstdCompressor() if 'w' in mode else zstandard.ZstdDecompressor()
    raw = open(path, mode.replace('r', 'rb').replace('w', 'wb'))
    if 'w' in mode:
        stream = zst_ctx.stream_writer(raw, closefd=True)
        tar_mode = 'w|'
    else:
        stream = zst_ctx.stream_reader(raw, closefd=True)
        tar_mode = 'r|'
    return stream, tar_mode


def _is_zstd(path):
    try:
        with open(path, 'rb') as f:
            magic = f.read(4)
        # Standard zstd frame magic
        if magic == b'\x28\xb5\x2f\xfd':
            return True
        # Zstd skippable frame magic range: 0x184D2A50 - 0x184D2A5F (little-endian)
        val = int.from_bytes(magic, 'little')
        return 0x184D2A50 <= val <= 0x184D2A5F
    except OSError:
        return False


def _extract_to(src_path, dest_dir):
    """Extract a .tar.zst or plain tar into dest_dir, returning list of extracted paths."""
    dest = Path(dest_dir).resolve()
    extracted = []

    def _safe_extract(tar):
        extracted_names = set()
        for member in tar:
            target = (dest / member.name).resolve()
            if not str(target).startswith(str(dest)):
                raise ValueError(f"Unsafe tar entry rejected: {member.name}")
            if member.name in extracted_names:
                continue  # skip intra-archive duplicates silently
            tar.extract(member, dest_dir)
            extracted.append(member.name)
            extracted_names.add(member.name)

    if _is_zstd(src_path):
        stream, tar_mode = _open_zst_tar(src_path, 'r')
        with stream:
            with tarfile.open(fileobj=stream, mode=tar_mode) as tar:
                _safe_extract(tar)
    else:
        with tarfile.open(src_path, 'r:*') as tar:
            _safe_extract(tar)

    return extracted


def merge(inputs, output, on_conflict='warn'):
    """
    Merge N input archives into one output .tar.zst.

    Parameters:
        inputs     : list of paths to input archives
        output     : path for the merged .tar.zst
        on_conflict: 'warn' (default) or 'error' — what to do when the same
                     arcname appears in more than one input archive
    """
    seen = {}   # arcname -> source archive path

    with tempfile.TemporaryDirectory() as staging:
        for src in inputs:
            src = os.path.abspath(src)
            print(f"  extracting: {src}")
            names = _extract_to(src, staging)
            for name in names:
                if name in seen:
                    msg = (f"conflict: '{name}' exists in both "
                           f"'{seen[name]}' and '{src}'")
                    if on_conflict == 'error':
                        sys.exit(f"error: {msg}")
                    else:
                        print(f"warning: {msg} — keeping first", file=sys.stderr)
                else:
                    seen[name] = src

        print(f"  writing merged archive: {output}")
        stream, tar_mode = _open_zst_tar(output, 'w')
        with stream:
            with tarfile.open(fileobj=stream, mode=tar_mode) as tar:
                for arcname in sorted(seen):
                    fpath = os.path.join(staging, arcname)
                    if os.path.exists(fpath):
                        tar.add(fpath, arcname=arcname)

    print(f"done: merged {len(inputs)} archive(s), {len(seen)} entries → {output}")


def _find_archives(paths):
    """
    Expand a mixed list of files and directories into a flat list of archive paths.
    Directories are searched recursively for *abixmls*.tar.zst files.
    The output archive (if inside a searched directory) is excluded via the caller.
    """
    archives = []
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isdir(p):
            found = sorted(Path(p).rglob('*abixmls*.tar.zst'))
            if not found:
                print(f"warning: no *abixmls*.tar.zst files found under {p}", file=sys.stderr)
            for f in found:
                archives.append(str(f))
        elif os.path.isfile(p):
            archives.append(p)
        else:
            sys.exit(f"error: not a file or directory: {p}")
    return archives


def main():
    parser = argparse.ArgumentParser(
        description="Merge per-arch abixmls.tar.zst archives into one.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # explicit files\n"
            "  %(prog)s --input a.tar.zst b.tar.zst --output merged.tar.zst\n"
            "\n"
            "  # directory: all *abixmls*.tar.zst found recursively\n"
            "  %(prog)s --input /path/to/build/dir --output merged.tar.zst\n"
            "\n"
            "  # mix of files and directories\n"
            "  %(prog)s --input /builds/repo1 /builds/repo2/specific.tar.zst --output merged.tar.zst\n"
        )
    )
    parser.add_argument('--input', nargs='+', required=True, metavar='PATH',
                        help='Input archives or directories containing *abixmls*.tar.zst files '
                             '(directories are searched recursively)')
    parser.add_argument('--output', required=True, metavar='ARCHIVE',
                        help='Output merged .tar.zst archive')
    parser.add_argument('--on-conflict', choices=['warn', 'error'], default='warn',
                        help='Action when the same path appears in multiple inputs (default: warn)')
    args = parser.parse_args()

    inputs = _find_archives(args.input)

    # exclude the output file itself in case it lives inside a searched directory
    output_abs = os.path.abspath(args.output)
    inputs = [p for p in inputs if os.path.abspath(p) != output_abs]

    if not inputs:
        sys.exit("error: no input archives found")

    print(f"Found {len(inputs)} archive(s) to merge:")
    for p in inputs:
        print(f"  {p}")

    merge(inputs, args.output, on_conflict=args.on_conflict)


if __name__ == '__main__':
    main()
