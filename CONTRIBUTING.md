# Contributing to meta-binaryaudit

`meta-binaryaudit` is an open source project. The layer metadata and the
Python module under `lib/` are licensed under [MIT](https://opensource.org/licenses/MIT),
everything under `scripts/` is licensed under
[GPL-2.0-only](https://opensource.org/licenses/GPL-2.0). See README.md.

## Coding Style

We follow the [OpenEmbedded Style](https://docs.yoctoproject.org/contributor-guide/recipe-style-guide.html)
convention for the Yocto layer files and the
[PEP 8](https://peps.python.org/pep-0008/) convention for Python. CI runs
`flake8` on `lib/` for each pull request.

## Certificate of Origin

Every commit must have a `Signed-off-by` line, as described in the
[Developer Certificate of Origin](https://developercertificate.org/), the same
way as in the Linux kernel and OpenEmbedded.

## Patch format

Use the OpenEmbedded
[commit message guidelines](https://docs.yoctoproject.org/contributor-guide/submit-changes.html#implement-and-commit-changes):

```
<component>: short summary

More detailed explanation of your changes: why and how.
Wrap it to 72 characters.

Signed-off-by: Your Name <your.email@example.com>
```

For example:

```
abicheck: skip non-library ELF files

Only shared libraries have an ABI to compare. Running abidw on
executables and kernel modules only adds build time.

Signed-off-by: Your Name <your.email@example.com>
```

## Pull requests

1. Fork https://github.com/Nordix/meta-binaryaudit.
2. Create a branch for your change in your fork.
3. Open a pull request against the `main` branch.
4. Address the review comments by amending your commits and force-pushing
   the branch. A maintainer (see README.md) merges the pull request once it
   is approved.

## Issue tracking

Report problems in
[GitHub issues](https://github.com/Nordix/meta-binaryaudit/issues/new).

To close an issue from a commit, add a `Fixes: #<number>` line to the commit
message.
