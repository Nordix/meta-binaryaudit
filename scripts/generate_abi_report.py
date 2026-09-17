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

    pkg_versions = {}          # pkg -> {'old','new'}  (aggregated for display)
    pkg_arch_versions = {}     # (pkg, arch) -> {'old','new'}  (precise, per-arch)

    # Each "Package:" header applies to the libraries that follow it until the
    # next header. A single package may appear multiple times (once per arch)
    # with different versions, so associate every header with the arch of the
    # first "Comparing:" line that follows it and track versions per-arch.
    hdr_re = re.compile(
        r'^(?:  )?Package: (\S+), Old: ([^\n,]+), New: ([^\n]+)'
        r'(?P<body>(?:.*\n)*?)(?=^(?:  )?Package: |\Z)',
        re.MULTILINE)
    for m in hdr_re.finditer(content):
        pkg = m.group(1)
        old = m.group(2).strip()
        new = m.group(3).strip()
        cmp_m = re.search(r'Comparing: (\S+?)/([^/]+)/', m.group('body'))
        arch = cmp_m.group(2) if cmp_m else None
        if arch is not None:
            pkg_arch_versions[(pkg, arch)] = {'old': old, 'new': new}
        # Aggregate distinct versions across arches for the package-level display.
        agg = pkg_versions.setdefault(pkg, {'old': [], 'new': []})
        if old not in agg['old']:
            agg['old'].append(old)
        if new not in agg['new']:
            agg['new'].append(new)

    # Collapse aggregated version lists into display strings (e.g. "0.13.2, 0.15.3").
    for pkg, v in pkg_versions.items():
        v['old'] = ', '.join(v['old']) if v['old'] else '?'
        v['new'] = ', '.join(v['new']) if v['new'] else '?'

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
        parts_old = lib_name_old.split('/')
        pkg = parts_old[0]
        arch = parts_old[1] if len(parts_old) > 2 else None
        binary = parts_old[-1]

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

        # Extract changed variables with full sub-type detail block.
        # Format: "  [C] '<decl>' was changed at <file:line>:\n<indented detail...>"
        # Detail lines are indented; stop at the next change marker, a summary
        # line, a blank line, the abidiff_rc line, or a status marker.
        changed_vars = []
        for vm in re.finditer(
            r"  \[C\] '((?:const |volatile )?[^']+)' was changed(?: at ([^\s:]+:\d+):\d+)?:\n"
            r"((?:(?!  \[[CAD]\] |\d+ (?:Added|Removed|Changed|variable|function)\b|abidiff_rc:|[\u26a0\u2713\u2717]|\n)[^\n]*\n)*)",
            lib_content
        ):
            changed_vars.append({
                'sig': vm.group(1),
                'loc': vm.group(2) or 'unknown',
                'detail': vm.group(3).rstrip()
            })

        # Added / removed variables (declaration + ELF symbol in braces).
        added_vars   = re.findall(r"\[A\] 'variable ([^']+)'\s+\{([^}]+)\}", lib_content)
        removed_vars = re.findall(r"\[D\] 'variable ([^']+)'\s+\{([^}]+)\}", lib_content)

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
            'arch': arch,
            'ver_old': pkg_arch_versions.get((pkg, arch), {}).get('old', '?'),
            'ver_new': pkg_arch_versions.get((pkg, arch), {}).get('new', '?'),
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
            'removed_vars': removed_vars,
            'added_vars': added_vars,
            'changed_vars': changed_vars,
            'removed_syms': removed_syms,
            'added_syms': added_syms,
        })

    # Add preamble-skipped SONAME libraries (new log format)
    for lib_path, new_soname in sorted(preamble_soname.items()):
        parts = lib_path.split('/')
        pkg = parts[0]
        arch = parts[1] if len(parts) > 2 else None
        binary = parts[-1]
        if pkg not in packages:
            packages[pkg] = {
                'old_ver': pkg_versions.get(pkg, {}).get('old', '?'),
                'new_ver': pkg_versions.get(pkg, {}).get('new', '?'),
                'binaries': []
            }
        packages[pkg]['binaries'].append({
            'name': binary, 'arch': arch,
            'ver_old': pkg_arch_versions.get((pkg, arch), {}).get('old', '?'),
            'ver_new': pkg_arch_versions.get((pkg, arch), {}).get('new', '?'),
            'new_soname': new_soname, 'idx': 0,
            'has_change': True, 'is_incompatible': False, 'has_incompat_funcs': False, 'soname_changed': True, 'is_compatible': False,
            'func_removed': 0, 'func_changed': 0, 'func_added': 0,
            'var_removed': 0, 'var_changed': 0, 'var_added': 0,
            'fsym_removed': 0, 'fsym_added': 0, 'vsym_removed': 0, 'vsym_added': 0,
            'removed_funcs': [], 'added_funcs': [], 'changed_funcs': [],
            'removed_vars': [], 'added_vars': [], 'changed_vars': [],
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


# Aggregate-status ranking (worst wins), mirroring the badge priority in the UI.
_STATUS_RANK = {
    'CLEAN': 0,
    'COMPATIBLE_CHANGE': 1,   # additions only
    'SONAME_BREAK': 2,
    'SUBTYPE_RISK': 3,        # type changed
    'HAS_REMOVALS': 4,        # symbols removed
    'INCOMPATIBLE': 5,        # abi changed
    'CRASHED': 6,
}


def _aggregate_status(binaries):
    """Reduce a set of per-arch library results to a single worst-case label."""
    worst = 'CLEAN'
    for b in binaries:
        status, flags = _library_status(b)
        if status == 'CHANGED':
            # Promote to the most severe sub-flag it carries.
            for f in ('HAS_REMOVALS', 'SUBTYPE_RISK', 'COMPATIBLE_CHANGE'):
                if f in flags:
                    status = f
                    break
        if _STATUS_RANK.get(status, 0) > _STATUS_RANK.get(worst, 0):
            worst = status
    return worst


def generate_json(packages, comparison_title, suppressed_fps, output_file):
    ref_name, cur_name = (comparison_title.split(' vs ') + ['', ''])[:2]
    out = {
        'comparison': {'ref': ref_name.strip(), 'current': cur_name.strip()},
        'suppressed_false_positives': suppressed_fps or [],
        'packages': []
    }
    for pkg, data in sorted(packages.items()):
        # Build per-arch version transitions so the report can show which
        # old version maps to which new version (and on which architectures),
        # instead of flattening everything into two disconnected lists. Each
        # transition also carries an aggregate ABI status for its arch group.
        transitions = []          # ordered list of {'old','new','arches','status'}
        seen = {}                 # (old,new) -> index into transitions
        _trans_bins = []          # parallel list of binary lists per transition
        for b in data['binaries']:
            old = b.get('ver_old', '?')
            new = b.get('ver_new', '?')
            arch = b.get('arch')
            key = (old, new)
            if key not in seen:
                seen[key] = len(transitions)
                transitions.append({'old': old, 'new': new, 'arches': []})
                _trans_bins.append([])
            entry = transitions[seen[key]]
            if arch and arch not in entry['arches']:
                entry['arches'].append(arch)
            _trans_bins[seen[key]].append(b)
        for t, bins in zip(transitions, _trans_bins):
            t['status'] = _aggregate_status(bins)

        pkg_entry = {
            'package': pkg,
            'version_old': data['old_ver'],
            'version_new': data['new_ver'],
            'version_transitions': transitions,
            'libraries': []
        }
        for b in data['binaries']:
            status, flags = _library_status(b)
            lib_entry = {
                'library': b['name'],
                'arch': b.get('arch'),
                'version_old': b.get('ver_old', '?'),
                'version_new': b.get('ver_new', '?'),
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
                'removed_variables': [{'declaration': v[0], 'symbol': v[1]} for v in b.get('removed_vars', [])],
                'added_variables':   [{'declaration': v[0], 'symbol': v[1]} for v in b.get('added_vars', [])],
                'changed_variables': [{'declaration': v['sig'], 'location': v['loc'], 'detail': v['detail']} for v in b.get('changed_vars', [])],
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
