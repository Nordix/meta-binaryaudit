#!/usr/bin/env python3
# Copyright (C) 2026 Ericsson Software Technology AB
# SPDX-License-Identifier: GPL-2.0-only
#
# Merge multiple per-arch abixmls.tar.zst archives (one per CI arch build)
# into a single archive that abi_compare.py can consume transparently.
#
# Usage:
#   python3 merge_abixmls.py \
#       --input  distro-1.0-cortexa53-abixmls.tar.zst \
#                distro-1.0-x86_64-abixmls.tar.zst \
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
            return f.read(4) == b'\x28\xb5\x2f\xfd'
    except OSError:
        return False


def _extract_to(src_path, dest_dir):
    """Extract a .tar.zst or plain tar into dest_dir, returning list of extracted paths."""
    dest = Path(dest_dir).resolve()
    extracted = []

    def _safe_extract(tar):
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if not str(target).startswith(str(dest)):
                raise ValueError(f"Unsafe tar entry rejected: {member.name}")
            tar.extract(member, dest_dir)
            extracted.append(member.name)

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


def main():
    parser = argparse.ArgumentParser(
        description="Merge per-arch abixmls.tar.zst archives into one.")
    parser.add_argument('--input', nargs='+', required=True, metavar='ARCHIVE',
                        help='Input .tar.zst archives (one per arch build)')
    parser.add_argument('--output', required=True, metavar='ARCHIVE',
                        help='Output merged .tar.zst archive')
    parser.add_argument('--on-conflict', choices=['warn', 'error'], default='warn',
                        help='Action when the same path appears in multiple inputs (default: warn)')
    args = parser.parse_args()

    missing = [p for p in args.input if not os.path.exists(p)]
    if missing:
        sys.exit("error: input file(s) not found: " + ", ".join(missing))

    merge(args.input, args.output, on_conflict=args.on_conflict)


if __name__ == '__main__':
    main()
