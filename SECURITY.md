<!-- SPDX-License-Identifier: MIT -->
# Security Policy

If you believe you have found a security vulnerability in `meta-binaryaudit`,
please report it to us as described below.

## Reporting a vulnerability

**Please do not open a public issue, pull request, or discussion for a security problem.**

Instead,use the "Report a vulnerability" button on this repository's Security tab, or go directly to:

https://github.com/Nordix/meta-binaryaudit/security/advisories/new

We aim to acknowledge reports within 5 business days and to coordinate a
disclosure timeline with you, targeting remediation within 90 days.

### What to include

* Affected file, class or recipe, and the layer revision
* Yocto release and build configuration
* Reproduction steps; proof-of-concept if available
* Impact and how the issue could be exploited
* Any embargo/disclosure timing you would like us to honor
* Whether and how you wish to be credited

## Supported Versions

Only the `main` branch is supported with security updates. It is compatible
with the Yocto releases listed in README.md.

## Scope

This policy covers the `meta-binaryaudit` repository itself: the bbclasses,
the Python module under `lib/`, the libabigail recipe, and the tools under
`scripts/`.

**Out of scope:**

* **Vulnerabilities in libabigail, OpenEmbedded-Core or BitBake.** Report
  these to their upstream projects. For Yocto Project layers, see
  <https://docs.yoctoproject.org/security-reference/>.
* **Untrusted input to the build.** Recipes, buildhistory directories,
  reference baselines (`BINARY_AUDIT_REFERENCE_BASEDIR`) and suppression files
  are trusted build input, the same as any other layer content.
* **Untrusted ABI archives given to the scripts.** `abi_compare.py` and
  `merge_abixmls.py` are meant for archives produced by your own builds. Path
  traversal in tar entries is rejected; other issues from deliberately crafted
  archives are not.
