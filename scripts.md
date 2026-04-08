# ABI Comparison Scripts

These scripts form a two-step pipeline for comparing ABI XML snapshots produced
by the `binaryaudit` bbclass across two Yocto builds.

```
abi_compare.py  →  <run>.log  →  generate_abi_report.py  →  <run>.html + <run>.json
```

In a multi-arch CI pipeline, use `merge_abixmls.py` to combine the per-arch
archives before comparison:

```
[arch-1 build] → distro-ver-arch1-abixmls.tar.zst ─┐
[arch-2 build] → distro-ver-arch2-abixmls.tar.zst ─┤→ merge_abixmls.py → merged.tar.zst
[arch-N build] → distro-ver-archN-abixmls.tar.zst ─┘         │
                                                     abi_compare.py  →  <run>.log  →  ...
```

---

## merge_abixmls.py

Merges multiple per-arch `abixmls.tar.zst` archives (one produced per CI arch
build) into a single archive that `abi_compare.py` can consume transparently.

**Input:** two or more `.tar.zst` archives from `do_archive_abixmls`.
**Output:** a single merged `.tar.zst` preserving the full
`packages/<pkg_arch>/<pkg>/binaryaudit/abixml/<pkg_arch>/` structure.

### Usage

```bash
python3 merge_abixmls.py \
  --input  distro-1.0-cortexa53-abixmls.tar.zst \
           distro-1.0-x86_64-abixmls.tar.zst \
  --output distro-1.0-all-abixmls.tar.zst
```

| Argument | Required | Description |
|---|---|---|
| `--input ARCHIVE [...]` | yes | One or more input `.tar.zst` archives |
| `--output ARCHIVE` | yes | Path for the merged output archive |
| `--on-conflict warn\|error` | no | Action when the same path appears in multiple inputs (default: `warn`, keeps first) |

### CI step order

1. Build each arch in parallel, each producing `<distro>-<ver>-abixmls.tar.zst`
2. Collect all per-arch archives as CI artifacts
3. Run `merge_abixmls.py --input *.tar.zst --output merged.tar.zst`
4. Store `merged.tar.zst` as the baseline artifact for the next comparison
5. Run `abi_compare.py --ref-build <name> baseline.tar.zst --current-build <name> merged.tar.zst`

---

## abi_compare.py

Drives `abidiff` across all shared libraries found in two build trees, collects
results into a structured log, and reports SONAME changes separately from
actual ABI diffs.

**Input:** two Yocto build directories (or `buildhistory/` roots).  
The script searches recursively for `*/binaryaudit/abixml/*.so.xml` files, so
both `tmp/work/.../binaryaudit/` and `buildhistory/packages/<arch>/` layouts
are supported without any configuration.

**Output:** a plain-text log consumed by `generate_abi_report.py`.

### Usage

```bash
python3 abi_compare.py \
  --ref-build     <NAME> <PATH> \
  --current-build <NAME> <PATH> \
  --abidiff       /path/to/abidiff \
  2>&1 | tee output.log
```

| Argument | Required | Description |
|---|---|---|
| `--ref-build NAME PATH` | yes | Label and path for the reference (older) build |
| `--current-build NAME PATH` | yes | Label and path for the current (newer) build |
| `--abidiff PATH` | no | Path to `abidiff` binary (default: `abidiff` on `$PATH`; see [Yocto build environment note](#abidiff-from-the-yocto-build-environment) below) |
| `-p / --package PKG` | no | Restrict comparison to a single package |
| `-l / --library SONAME` | no | Restrict comparison to a single library |
| `-o / --output FILE` | no | Write diff output to `FILE` (single library) or `FILE.<pkg_soname>` (multiple libraries) |
| `--list` | no | List all discovered libraries and exit |
| `--no-suppressions` | no | Disable all suppression files (raw abidiff output) |

### Example — comparing two buildhistory snapshots

```bash
python3 abi_compare.py \
  --ref-build     <ref-name>     ~/builds/<ref-release>/buildhistory \
  --current-build <current-name> ~/builds/<current-release>/buildhistory \
  --abidiff       /path/to/abidiff \
  2>&1 | tee ~/reports/<ref-release>_vs_<current-release>.log
```

### abidiff from the Yocto build environment

`libabigail-native` is a native package built as part of the Yocto build
environment. It is not shipped inside any SDK. To use it, source the build
environment (`oe-init-build-env`) and run the script via `oe-run-native`:

```bash
oe-run-native libabigail-native abidiff --version
```

Alternatively, pass the full path to the `abidiff` binary built under
`tmp/sysroots-components/x86_64/libabigail-native/` using `--abidiff`.

### SONAME version matching

Libraries are matched across builds by their base soname (everything up to and
including `.so`), so a version bump from e.g. `libssl.so.3` to `libssl.so.3.1`
is detected as a SONAME change and reported separately rather than silently
dropped. Libraries whose base soname matches in both builds are compared
normally; those with a changed soname are listed under the
`⚠ SONAME changed` section and skipped.

### abidiff flags

Every `abidiff` invocation passes `--drop-private-types` and
`--no-unreferenced-symbols` to reduce noise from compiler-internal types and
symbols that are never reachable from the public API.

### How suppressions are applied

Every `abidiff` invocation receives all suppression files via
`--suppressions`. The generic file is always passed; per-library files are
also always passed (libabigail ignores rules whose `soname_regexp` does not
match the library being compared, so there is no cross-contamination).

A `suppressed_fp:` line is written to the log for each rule that matched the
current library's soname — these lines are picked up by `generate_abi_report.py`
and shown in the HTML/JSON footer.

---

## generate_abi_report.py

Parses the log produced by `abi_compare.py` and emits an HTML report and a
machine-readable JSON file.

**Input:** the `.log` file from `abi_compare.py`.  
**Output:** `<name>.html` and `<name>.json` (JSON path is derived automatically
from the HTML path).

### Usage

```bash
python3 generate_abi_report.py <log_file> <output.html>
```

### Example

```bash
python3 generate_abi_report.py \
  ~/reports/<ref-release>_vs_<current-release>.log \
  ~/reports/<ref-release>_vs_<current-release>.html
# also writes ~/reports/<ref-release>_vs_<current-release>.json
```

### HTML report

Interactive single-page report with:
- Summary stat cards (packages, binaries, clean, changed, incompatible, SONAME breaks)
- Per-package collapsible sections with per-library status badges
- Filter bar: All / Changed Only / Sub-type Risk / Has Removals / Incompatible / SONAME Break
- Collapsible tables of removed, added, and changed functions with sub-type detail

### JSON report

Intended for downstream tooling (e.g. notifying applications linked against a
changed library). Structure:

```json
{
  "comparison": { "ref": "<ref-name>", "current": "<current-name>" },
  "suppressed_false_positives": [ "..." ],
  "packages": [
    {
      "package": "openssl",
      "version_old": "3.1.4",
      "version_new": "3.2.1",
      "libraries": [
        {
          "library": "libssl.so.3",
          "status": "CHANGED",
          "status_flags": ["HAS_REMOVALS"],
          "abidiff_rc": 12,
          "changes": {
            "functions": { "removed": 2, "changed": 0, "added": 5 },
            "variables": { "removed": 0, "changed": 0, "added": 0 },
            "symbols_no_debug": {
              "functions": { "removed": 0, "added": 0 },
              "variables": { "removed": 0, "added": 0 }
            }
          },
          "removed_functions": [ { "signature": "...", "symbol": "..." } ],
          "added_functions":   [],
          "changed_functions": [],
          "removed_symbols":   [],
          "added_symbols":     []
        }
      ]
    }
  ]
}
```

#### Status values

| `status` | `status_flags` | Meaning |
|---|---|---|
| `CLEAN` | `[]` | No ABI changes detected |
| `CHANGED` | `["COMPATIBLE_CHANGE"]` | Only additions, nothing removed or broken |
| `CHANGED` | `["HAS_REMOVALS"]` | Functions or variables were removed — verify impact on callers |
| `CHANGED` | `["SUBTYPE_RISK"]` | Function sub-type changed in a way that may break callers |
| `CHANGED` | `["HAS_REMOVALS","SUBTYPE_RISK"]` | Both of the above |
| `INCOMPATIBLE` | `[]` | abidiff explicitly flagged an incompatible ABI break |
| `SONAME_BREAK` | `[]` | SONAME version bumped — different library, not compared |

`status_flags` is a list so a library can carry multiple sub-classifications
simultaneously (e.g. both `HAS_REMOVALS` and `SUBTYPE_RISK`).

---

## Suppression Files

libabigail's `abidiff` reports every structural difference it can detect,
including changes to types and symbols that are internal implementation details
never exposed to callers. Without suppressions, the output contains a large
volume of noise that obscures real ABI breaks.

Suppression files are in INI-like format understood by libabigail. Each
`[suppress_function]` or `[suppress_type]` block tells abidiff to ignore
matching changes. Rules can be scoped to a specific library via
`soname_regexp`.

### suppressions/generic-false-positives.abignore

Applied to **every** library. Contains only patterns that are universally safe
to suppress regardless of which library is being compared.

| Rule | Why it is safe |
|---|---|
| `symbol_version_regexp = .*_PRIVATE$` | Any symbol versioned `*_PRIVATE` (e.g. `GLIBC_PRIVATE`, `OPENSSL_PRIVATE`) is an explicit internal contract between the library and its own loader/plugins. No external caller should ever link against these. |
| `name_regexp = ^_ZNSt` | C++ mangled names starting with `_ZNSt` are `std::` internals from the C++ runtime. They are never part of a library's public ABI contract. |
| `name_regexp = ^_IO_FILE` | `_IO_FILE` is glibc's internal stdio implementation struct. It is not present in any installed public header and callers only ever hold an opaque `FILE*`. |
| `name_regexp = ^pthread_cond_t$` | POSIX defines `pthread_cond_t` as an opaque type. Its layout is an implementation detail; callers always pass it by pointer and never inspect its fields. |
| `name_regexp = __private__` | Functions explicitly named with `__private__` are marked internal by convention. Suppressed for functions only — type layout changes under `__private__` names are left to per-library files. |

### suppressions/glibc-2.39-asm-dwarf.abignore

Scoped to `libm.so.*`.

`__floorl` and `__truncl` are implemented in hand-written assembly on x86-64 in
glibc 2.39 (`sysdeps/x86_64/fpu/s_floorl.S`, `s_truncl.S`). Assembly files
carry no DWARF type information, so abidiff sees the return type as `void`
instead of `long double` and reports an incompatible change. The C
reimplementation that fixes the DWARF gap was only merged in glibc 2.40
(BZ 31600, commit `637bfc392f`). This suppression is safe to remove once the
reference build moves to glibc 2.40+.

### suppressions/gdbm-internal-funcs.abignore

Scoped to `libgdbm.so.*`.

gdbm uses a `_`-prefixed naming convention for internal functions
(e.g. `_gdbm_lock_file`). These are not declared in the installed `gdbm.h`
header and are not part of the public API. A bare `^_` rule is intentionally
**not** placed in the generic file because the single-underscore prefix is used
for legitimate public symbols in other libraries.

### suppressions/openssl-internal-ctx.abignore

Scoped to `libcrypto.so.*`.

`ossl_lib_ctx_st` is OpenSSL's internal library context struct, accessed
exclusively through the opaque `OSSL_LIB_CTX*` typedef. No caller ever
embeds or dereferences this struct directly — the public API only passes
pointers to it. Layout changes to this struct are therefore not a
caller-visible ABI break.
