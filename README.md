# meta-binaryaudit

Yocto layer for ELF binary compliance validation.

# Dependencies

* URI: https://git.openembedded.org/openembedded-core
* Branch: scarthgap|whinlatter|wrynose|blacksail

# Maintainers

* Adarsh Jagadish Kamini <adarsh.jagadish.kamini@est.tech>

# Contributing

Send patches as pull requests against the `main` branch of
https://github.com/Nordix/meta-binaryaudit. See CONTRIBUTING.md for the
commit message format.

# License

The layer metadata (classes, conf, recipes) and the Python module under `lib/`
are MIT licensed, see `LICENSE.MIT`.

Everything under `scripts/` is GPL-2.0-only, see `LICENSE.GPL-2.0-only`. The
source files there carry an SPDX license identifier.

# ABI compliance

The ABI compliance mechanism relies on [libabigail](https://sourceware.org/libabigail/).

The included libabigail recipe is configurable through
[PACKAGECONFIG](https://docs.yoctoproject.org/ref-manual/variables.html#term-PACKAGECONFIG).
See the recipe for the available options.

## ABI serialization

Enable the ABI check by adding the `abicheck` class to `INHERIT` in `local.conf`:

```bitbake
INHERIT += "abicheck"
```

The class adds a `do_gather_abixml` task after `do_install` which writes an
ABI dump of every shared library to buildhistory. Keep the buildhistory of a
build to use it as a baseline for later builds.

After the baseline build, point the layer at its buildhistory directory:

```bitbake
BINARY_AUDIT_REFERENCE_BASEDIR = "/path/to/buildhistory.baseline"
```

The comparison runs as part of
[package QA](https://docs.yoctoproject.org/ref-manual/qa-checks.html) and
uses [abidiff](https://sourceware.org/libabigail/manual/abidiff.html).
Incompatible ABI changes are reported as `abi-changed` warnings by default.

To make them build errors instead, add the following to `local.conf`:

```bitbake
ERROR_QA:append = " abi-changed"
WARN_QA:remove = " abi-changed"
```

Set `ABI_CHECK_SKIP = "1"` in a recipe to skip it.

## CI / command-line usage

To enable abicheck for a single build without modifying `local.conf`, use the
`-R` flag to read the provided conf fragment:

```bash
bitbake -R /path/to/meta-binaryaudit/conf/abicheck-enable.conf <target>
```

To set the reference baseline from the environment, the variable has to be
allowed through first:

```bash
export BB_ENV_PASSTHROUGH_ADDITIONS="$BB_ENV_PASSTHROUGH_ADDITIONS BINARY_AUDIT_REFERENCE_BASEDIR"
BINARY_AUDIT_REFERENCE_BASEDIR=/path/to/buildhistory.baseline \
bitbake -R /path/to/meta-binaryaudit/conf/abicheck-enable.conf <target>
```

To make ABI changes build errors (e.g. in a gating CI job), add a second
fragment:

```bash
bitbake -R /path/to/meta-binaryaudit/conf/abicheck-enable.conf \
        -R /path/to/meta-binaryaudit/conf/abicheck-errors.conf <target>
```

The two conf fragments are:
- `conf/abicheck-enable.conf`: adds `abicheck` to `INHERIT` and
  `nativesdk-libabigail` to the SDK
- `conf/abicheck-errors.conf`: moves `abi-changed` from `WARN_QA` to `ERROR_QA`

## Comparing builds outside bitbake

At the end of each build, all ABI dumps are also packed into a single archive:

```
${BUILDHISTORY_DIR}/${DISTRO}-${DISTRO_VERSION}-abixmls.tar.zst
```

Keep this archive instead of the whole buildhistory directory to compare
against later builds. The scripts under `scripts/` compare two archives (or
two buildhistory directories) and generate an HTML and JSON report:

```bash
python3 scripts/abi_compare.py \
    --ref-build     old /path/to/old-abixmls.tar.zst \
    --current-build new /path/to/new-abixmls.tar.zst > compare.log
python3 scripts/generate_abi_report.py compare.log report.html
```

The scripts need `abidiff` from libabigail on the host (or pass its path with
`--abidiff`) and the `zstandard` Python package. See `scripts.md` for all
options, merging per-arch archives, and the bundled suppression files.

## ABI error suppressions

An ABI [suppression specification file](https://sourceware.org/libabigail/manual/libabigail-concepts.html#suppr-spec-label)
can be used to tell abidiff to ignore certain changes.

To use a global suppression file, set its path in `local.conf`:

```bitbake
BINARY_AUDIT_GLOBAL_SUPPRESSION_FILE = "/path/to/suppression.file"
```

To add a suppression for one recipe, add the file to the recipe's `SRC_URI`
from a bbappend. The file name must match `abi*.suppr`. For example, for
openssl:

```bitbake
# openssl_%.bbappend
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://abi_openssl.suppr"
```

The file is unpacked to the recipe's `WORKDIR` and passed to abidiff with
`--suppr`.
