#!/usr/bin/env python3
# Copyright (C) 2026 Ericsson Software Technology AB
# SPDX-License-Identifier: GPL-2.0-only
import re
import json
import sys
import os
import shutil

def parse_log(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    comparison_title = ''
    m = re.search(r'^# ABI Comparison: (.+)', content, re.MULTILINE)
    if m:
        comparison_title = m.group(1).strip()

    suppressed_fps = list(dict.fromkeys(re.findall(r'^suppressed_fp: (.+)', content, re.MULTILINE)))

    pkg_versions = {}
    for m in re.finditer(r'^(?:  )?Package: (\S+), Old: ([^\n,]+), New: ([^\n]+)', content, re.MULTILINE):
        pkg_versions[m.group(1)] = {'old': m.group(2).strip(), 'new': m.group(3).strip()}

    # Parse preamble SONAME-skipped libraries (new log format)
    preamble_soname = {}  # old_key -> new_soname
    for m in re.finditer(r'⚠ SONAME changed[^\n]*\n((?:[^\n]*\n)*?)(?=\nFound|\Z)', content):
        for line in m.group(1).splitlines():
            if ' -> ' in line:
                parts = line.strip().split(' -> ')
                preamble_soname[parts[0]] = parts[1].split('/')[-1]

    sections = re.split(r'={60}\n\[(\d+)/\d+\] Comparing: ([^\n]+)\n(?:\u26a0[^\n]+\n)?={60}', content)
    total_libs = int(re.search(r'Found (\d+) libraries to compare', content).group(1))

    packages = {}
    for i in range(1, len(sections), 3):
        idx = int(sections[i])
        lib_path = sections[i+1].strip()
        lib_content = sections[i+2]

        lib_name_old = lib_path.split(' -> ')[0]
        pkg = lib_name_old.split('/')[0]
        binary = lib_name_old.split('/')[-1]

        # Trim any trailing "Package:" header that bleeds in from the next section
        lib_content = re.split(r'\n\nPackage:', lib_content)[0]

        has_change = 'No ABI changes detected' not in lib_content
        rc_match = re.search(r'^abidiff_rc: (-?\d+)', lib_content, re.MULTILINE)
        abidiff_rc = int(rc_match.group(1)) if rc_match else (-1 if has_change else 0)
        crashed = abidiff_rc < 0
        soname_changed = 'SONAME changed' in lib_content
        is_incompatible = not crashed and not soname_changed and bool(abidiff_rc & 8)
        is_compatible = not crashed and bool(abidiff_rc & 4)
        has_incompat_funcs = bool(re.search(r'\d+ function.*incompatible sub-type', lib_content))

        func_match = re.search(
            r'Functions changes summary: (\d+) Removed(?:\s*\(\d+ filtered out\))?, (\d+) Changed(?:\s*\(\d+ filtered out\))?, (\d+) Added',
            lib_content)
        var_match = re.search(r'Variables changes summary: (\d+) Removed, (\d+) Changed, (\d+) Added', lib_content)
        fsym_match = re.search(r'Function symbols changes summary: (\d+) Removed, (\d+) Added', lib_content)
        vsym_match = re.search(r'Variable symbols changes summary: (\d+) Removed, (\d+) Added', lib_content)

        func_removed = int(func_match.group(1)) if func_match else 0
        func_changed = int(func_match.group(2)) if func_match else 0
        func_added   = int(func_match.group(3)) if func_match else 0
        var_removed  = int(var_match.group(1)) if var_match else 0
        var_changed  = int(var_match.group(2)) if var_match else 0
        var_added    = int(var_match.group(3)) if var_match else 0
        fsym_removed = int(fsym_match.group(1)) if fsym_match else 0
        fsym_added   = int(fsym_match.group(2)) if fsym_match else 0
        vsym_removed = int(vsym_match.group(1)) if vsym_match else 0
        vsym_added   = int(vsym_match.group(2)) if vsym_match else 0

        removed_funcs = re.findall(r"\[D\] '(?:function|method) ([^']+)'\s+\{([^}]+)\}", lib_content)
        added_funcs   = re.findall(r"\[A\] '(?:function|method) ([^']+)'\s+\{([^}]+)\}", lib_content)

        # Extract changed functions with full sub-type detail block
        changed_funcs = []
        for cm in re.finditer(
            r"  \[C\] '(?:function|method) ([^']+)'(?: at ([^\s:]+:\d+):\d+)? has some (?:sub-type|indirect sub-type) changes:\n((?:(?!  \[[CAD]\] |\d+ (?:Added|Removed|Changed) )[^\n]*\n)*)",
            lib_content
        ):
            changed_funcs.append({
                'sig': cm.group(1),
                'loc': cm.group(2) or 'unknown',
                'detail': cm.group(3).rstrip()
            })

        removed_sym_blocks = re.findall(
            r'Removed.*?symbol[s]? not referenced.*?debug info:\n((?:\s+\[D\][^\n]+\n)+)', lib_content)
        removed_syms = []
        for blk in removed_sym_blocks:
            removed_syms += re.findall(r'\[D\] (\S+)', blk)

        added_sym_blocks = re.findall(
            r'Added.*?symbol[s]? not referenced.*?debug info:\n((?:\s+\[A\][^\n]+\n)+)', lib_content)
        added_syms = []
        for blk in added_sym_blocks:
            added_syms += re.findall(r'\[A\] (\S+)', blk)

        if pkg not in packages:
            packages[pkg] = {
                'old_ver': pkg_versions.get(pkg, {}).get('old', '?'),
                'new_ver': pkg_versions.get(pkg, {}).get('new', '?'),
                'binaries': []
            }

        packages[pkg]['binaries'].append({
            'name': binary,
            'new_soname': None,
            'idx': idx,
            'abidiff_rc': abidiff_rc,
            'has_change': has_change,
            'is_incompatible': is_incompatible,
            'has_incompat_funcs': has_incompat_funcs,
            'soname_changed': soname_changed,
            'is_compatible': is_compatible,
            'func_removed': func_removed,
            'func_changed': func_changed,
            'func_added': func_added,
            'var_removed': var_removed,
            'var_changed': var_changed,
            'var_added': var_added,
            'fsym_removed': fsym_removed,
            'fsym_added': fsym_added,
            'vsym_removed': vsym_removed,
            'vsym_added': vsym_added,
            'removed_funcs': removed_funcs,
            'added_funcs': added_funcs,
            'changed_funcs': changed_funcs,
            'removed_syms': removed_syms,
            'added_syms': added_syms,
        })

    # Add preamble-skipped SONAME libraries (new log format)
    for lib_path, new_soname in sorted(preamble_soname.items()):
        pkg = lib_path.split('/')[0]
        binary = lib_path.split('/')[-1]
        if pkg not in packages:
            packages[pkg] = {
                'old_ver': pkg_versions.get(pkg, {}).get('old', '?'),
                'new_ver': pkg_versions.get(pkg, {}).get('new', '?'),
                'binaries': []
            }
        packages[pkg]['binaries'].append({
            'name': binary, 'new_soname': new_soname, 'idx': 0,
            'has_change': True, 'is_incompatible': False, 'has_incompat_funcs': False, 'soname_changed': True, 'is_compatible': False,
            'func_removed': 0, 'func_changed': 0, 'func_added': 0,
            'var_removed': 0, 'var_changed': 0, 'var_added': 0,
            'fsym_removed': 0, 'fsym_added': 0, 'vsym_removed': 0, 'vsym_added': 0,
            'removed_funcs': [], 'added_funcs': [], 'changed_funcs': [],
            'removed_syms': [], 'added_syms': [],
        })

    return packages, total_libs, pkg_versions, comparison_title, suppressed_fps





def _library_status(b):
    """Returns primary status string + list of sub-flags, matching HTML badge logic."""
    if b.get('abidiff_rc') is not None and b['abidiff_rc'] < 0: return 'CRASHED', []
    if b['soname_changed']:  return 'SONAME_BREAK', []
    if b['is_incompatible']: return 'INCOMPATIBLE', []
    if b['has_change']:
        flags = []
        if b['func_removed'] or b['var_removed']: flags.append('HAS_REMOVALS')
        if b['has_incompat_funcs']:               flags.append('SUBTYPE_RISK')
        if not flags:                             flags.append('COMPATIBLE_CHANGE')
        return 'CHANGED', flags
    return 'CLEAN', []


def generate_json(packages, comparison_title, suppressed_fps, output_file):
    ref_name, cur_name = (comparison_title.split(' vs ') + ['', ''])[:2]
    out = {
        'comparison': {'ref': ref_name.strip(), 'current': cur_name.strip()},
        'suppressed_false_positives': suppressed_fps or [],
        'packages': []
    }
    for pkg, data in sorted(packages.items()):
        pkg_entry = {
            'package': pkg,
            'version_old': data['old_ver'],
            'version_new': data['new_ver'],
            'libraries': []
        }
        for b in data['binaries']:
            status, flags = _library_status(b)
            lib_entry = {
                'library': b['name'],
                'status': status,
                'status_flags': flags,
                'abidiff_rc': b.get('abidiff_rc', None),
                'changes': {
                    'functions': {'removed': b['func_removed'], 'changed': b['func_changed'], 'added': b['func_added']},
                    'variables': {'removed': b['var_removed'], 'changed': b['var_changed'], 'added': b['var_added']},
                    'symbols_no_debug': {
                        'functions': {'removed': b['fsym_removed'], 'added': b['fsym_added']},
                        'variables': {'removed': b['vsym_removed'], 'added': b['vsym_added']},
                    },
                },
                'removed_functions': [{'signature': f[0], 'symbol': f[1]} for f in b['removed_funcs']],
                'added_functions':   [{'signature': f[0], 'symbol': f[1]} for f in b['added_funcs']],
                'changed_functions':  [{'signature': f['sig'], 'location': f['loc'], 'detail': f['detail']} for f in b['changed_funcs']],
                'removed_symbols': b['removed_syms'],
                'added_symbols':   b['added_syms'],
            }
            if b['soname_changed'] and b.get('new_soname'):
                lib_entry['new_soname'] = b['new_soname']
            pkg_entry['libraries'].append(lib_entry)
        out['packages'].append(pkg_entry)

    with open(output_file, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"JSON written to:   {output_file}")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 generate_abi_report.py <log_file> <output_html>")
        sys.exit(1)
    packages, _total_libs, _pkg_versions, comparison_title, suppressed_fps = parse_log(sys.argv[1])

    output_html = sys.argv[2]
    base = output_html.rsplit('.', 1)[0] if '.' in output_html else output_html
    json_file = base + '.json'
    generate_json(packages, comparison_title, suppressed_fps, json_file)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    for asset in ('abi_report.html', 'abi_report.css', 'abi_report.js'):
        shutil.copy(os.path.join(script_dir, asset), os.path.join(os.path.dirname(output_html) or '.', asset))

    json_basename = os.path.basename(json_file)
    with open(os.path.join(script_dir, 'abi_report.html')) as src, open(output_html, 'w') as dst:
        dst.write(src.read().replace(
            "var jsonsource = 'abi_report_data.json'",
            f"var jsonsource = '{json_basename}'"
        ))
    print(f"HTML written to:   {output_html}")
    print(f"JSON written to:   {json_file}")
