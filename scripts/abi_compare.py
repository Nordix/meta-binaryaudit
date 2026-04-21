#!/usr/bin/env python3
# Copyright (C) 2026 Ericsson Software Technology AB
# SPDX-License-Identifier: GPL-2.0-only

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

def get_soname(xml_path):
    """Extract soname from ABI XML file."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        return root.get('soname')
    except:
        return None

def get_package_version(build_dir, package):
    """Extract package version from buildhistory latest file."""
    build_path = Path(build_dir)
    latest_files = list(build_path.rglob(f"*/{package}/latest"))
    if latest_files:
        try:
            content = latest_files[0].read_text()
            for line in content.split('\n'):
                if line.startswith('PV = '):
                    return line.split('=')[1].strip()
        except:
            pass
    return "unknown"

def find_abixml_files(build_dir, package=None):
    """Find all ABI XML files with sonames in build directory."""
    build_path = Path(build_dir)
    # Layout: [packages/<arch-os>/]<pkg>/binaryaudit/abixml/<arch>/*.so.xml
    pattern = "binaryaudit/abixml/*/*.so.xml"
    files = {}
    for xml_file in build_path.rglob(pattern):
        soname = get_soname(xml_file)
        if soname:
            # find 'binaryaudit' in parts and go one level up for pkg_name
            parts = xml_file.parts
            binaryaudit_idx = parts.index('binaryaudit')
            pkg_name = parts[binaryaudit_idx - 1]
            arch = xml_file.parts[-2]
            if package and pkg_name != package:
                continue
            key = f"{pkg_name}/{arch}/{soname}"
            headers_dir = xml_file.parent.parent.parent / "headers"
            files[key] = (xml_file, headers_dir if headers_dir.is_dir() else None)

    return files

_SUPPRESSIONS_DIR = Path(__file__).parent / 'suppressions'

def _load_suppressions():
    """Return all .abignore files found in the suppressions directory."""
    return sorted(_SUPPRESSIONS_DIR.glob('*.abignore'))

def run_abidiff(old_xml, new_xml, output=None, abidiff_path='abidiff', suppressions=None, headers_dir1=None, headers_dir2=None):
    """Run abidiff on two ABI XML files."""
    active = suppressions if suppressions is not None else _load_suppressions()
    using_headers = (headers_dir1 and Path(headers_dir1).is_dir()) or \
                    (headers_dir2 and Path(headers_dir2).is_dir())
    cmd = [abidiff_path, '--no-unreferenced-symbols']
    if not using_headers:
        cmd += ['--drop-private-types']
    for s in active:
        if Path(s).exists():
            cmd += ['--suppressions', str(s)]
    if headers_dir1 and Path(headers_dir1).is_dir():
        cmd += ['--hd1', str(headers_dir1)]
    if headers_dir2 and Path(headers_dir2).is_dir():
        cmd += ['--hd2', str(headers_dir2)]
    cmd += [str(old_xml), str(new_xml)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    output_text = result.stdout + result.stderr
    if output:
        Path(output).write_text(output_text)
    else:
        print(output_text)

    return result.returncode

def main():
    parser = argparse.ArgumentParser(description='Compare ABI XML files using libabigail abidiff')
    parser.add_argument('--ref-build', nargs=2, metavar=('NAME', 'PATH'), required=True, help='Reference build name and path (directory or abixmls.tar)')
    parser.add_argument('--current-build', nargs=2, metavar=('NAME', 'PATH'), required=True, help='Current build name and path (directory or abixmls.tar)')
    parser.add_argument('-p', '--package', help='Specific package to compare')
    parser.add_argument('-l', '--library', help='Specific library soname to compare')
    parser.add_argument('-o', '--output', help='Output file for diff report')
    parser.add_argument('--list', action='store_true', help='List available libraries')
    parser.add_argument('--abidiff', default='abidiff', help='Path to abidiff binary (default: abidiff on $PATH — use oe-run-native libabigail-native abidiff or pass the full path)')
    parser.add_argument('--no-suppressions', action='store_true', help='Disable all suppression files')
    args = parser.parse_args()
    ref_name, ref_path = args.ref_build
    cur_name, cur_path = args.current_build

    print(f"# ABI Comparison: {ref_name} vs {cur_name}")
    with _maybe_extract(ref_path) as ref_dir, _maybe_extract(cur_path) as cur_dir:
        return _run_compare(args, ref_name, ref_dir, cur_name, cur_dir)


def _maybe_extract(path):
    """Context manager: if path is a tar file, extract to a temp dir and yield it; otherwise yield path as-is."""
    import contextlib

    @contextlib.contextmanager
    def _extract_tar(tar_path):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp).resolve()
            if _is_zstd(tar_path):
                try:
                    import zstandard
                except ImportError:
                    sys.exit("error: 'zstandard' Python package is required for .tar.zst files")
                with zstandard.open(tar_path, 'rb') as zst_f:
                    with tarfile.open(fileobj=zst_f, mode='r|') as tar:
                        for member in tar:
                            if not (tmp_path / member.name).resolve().is_relative_to(tmp_path):
                                raise ValueError(f"Unsafe tar entry: {member.name}")
                            tar.extract(member, tmp)
            else:
                with tarfile.open(tar_path) as tar:
                    for member in tar.getmembers():
                        if not (tmp_path / member.name).resolve().is_relative_to(tmp_path):
                            raise ValueError(f"Unsafe tar entry: {member.name}")
                    tar.extractall(tmp)
            yield tmp

    @contextlib.contextmanager
    def _passthrough(p):
        yield p

    if os.path.isdir(path):
        return _passthrough(path)
    if _is_zstd(path) or tarfile.is_tarfile(path):
        return _extract_tar(path)
    return _passthrough(path)


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


def _run_compare(args, ref_name, ref_path, cur_name, cur_path):
    old_files = find_abixml_files(ref_path, args.package)
    new_files = find_abixml_files(cur_path, args.package)
    if args.list:
        print("Old build libraries:")
        for key in sorted(old_files.keys()):
            print(f"  {key}")
        print("\nNew build libraries:")
        for key in sorted(new_files.keys()):
            print(f"  {key}")
        return 0
    
    def base_key(pkg, arch, soname):
        return f"{pkg}/{arch}/{soname.split('.so')[0]}.so"

    old_by_base = {}
    for key, (path, hdr) in old_files.items():
        pkg, arch, soname = key.split('/', 2)
        old_by_base[base_key(pkg, arch, soname)] = (key, path, hdr)

    new_by_base = {}
    for key, (path, hdr) in new_files.items():
        pkg, arch, soname = key.split('/', 2)
        new_by_base[base_key(pkg, arch, soname)] = (key, path, hdr)

    common_base = set(old_by_base.keys()) & set(new_by_base.keys())
    if args.library:
        common_base = {k for k in common_base if args.library in k}

    soname_changed = [(old_by_base[k], new_by_base[k]) for k in common_base
                      if old_by_base[k][0] != new_by_base[k][0]]
    matches = [(old_by_base[k], new_by_base[k]) for k in common_base
               if old_by_base[k][0] == new_by_base[k][0]]

    if soname_changed:
        print(f"\n⚠ SONAME changed (intentional ABI break, not compared):")
        current_pkg = None
        for (old_key, _, _), (new_key, _, _) in sorted(soname_changed):
            pkg = old_key.split('/')[0]
            if pkg != current_pkg:
                old_ver = get_package_version(ref_path, pkg)
                new_ver = get_package_version(cur_path, pkg)
                print(f"\n  Package: {pkg}, Old: {old_ver}, New: {new_ver}")
                current_pkg = pkg
            print(f"  {old_key} -> {new_key}")

    if not matches:
        print("No common libraries found to compare", file=sys.stderr)
        return 1

    print(f"\nFound {len(matches)} libraries to compare\n")
    current_pkg = None
    for idx, ((old_key, old_path, old_hdr), (new_key, new_path, new_hdr)) in enumerate(sorted(matches), 1):
        pkg = old_key.split('/')[0]
        if pkg != current_pkg:
            old_ver = get_package_version(ref_path, pkg)
            new_ver = get_package_version(cur_path, pkg)
            print(f"\nPackage: {pkg}, Old: {old_ver}, New: {new_ver}")
            current_pkg = pkg
        print(f"\n{'='*60}")
        print(f"[{idx}/{len(matches)}] Comparing: {old_key} -> {new_key}")
        print('='*60)
        output_file = None
        if args.output and len(matches) == 1:
            output_file = args.output
        elif args.output:
            output_file = f"{args.output}.{old_key.replace('/', '_')}"
        suppressions = [] if args.no_suppressions else _load_suppressions()
        returncode = run_abidiff(old_path, new_path, output_file, args.abidiff, suppressions,
                                 headers_dir1=old_hdr, headers_dir2=new_hdr)
        print(f"abidiff_rc: {returncode}")
        if returncode == 0:
            print("✓ No ABI changes detected")
        elif returncode & 8 and returncode & 4:
            print("⚠ ABI changes detected (incompatible + compatible)")
        elif returncode & 8:
            print("⚠ ABI changes detected (incompatible)")
        elif returncode & 4:
            print("⚠ ABI changes detected (compatible)")
        else:
            print(f"✗ abidiff exited with unexpected code: {returncode}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
