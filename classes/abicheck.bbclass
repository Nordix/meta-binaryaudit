
inherit binaryaudit
inherit insane

BUILDHISTORY_FEATURES += "abicheck"

DEPENDS:append:class-target = "${@ ' libabigail-native' if d.getVar('ABI_CHECK_SKIP') != '1' else ''}"

IMG_DIR = "${WORKDIR}/image"

python do_gather_abixml() {
    import glob, os, time
    import shutil
    from binaryaudit import abicheck

    if d.getVar('CLASSOVERRIDE') != 'class-target' or d.getVar('ABI_CHECK_SKIP') == '1':
        return

    native_bindir = os.path.join(d.getVar("RECIPE_SYSROOT_NATIVE"), "usr", "bin")
    os.environ["PATH"] = native_bindir + ":" + os.environ.get("PATH", "")

    t0 = time.monotonic()

    dest_basedir = binary_audit_get_create_pkg_dest_basedir(d)

    pkg_arch = d.getVar("PACKAGE_ARCH")
    abixml_dir = os.path.join(dest_basedir, "abixml", pkg_arch)

    # Snapshot existing abixml as reference before overwriting with new build.
    # This allows comparing old vs new without separate reference configuration.
    ref_abixml_dir = os.path.join(dest_basedir, "abixml-reference", pkg_arch)
    abixml_arch_parent = os.path.join(dest_basedir, "abixml")
    ref_abixml_arch_parent = os.path.join(dest_basedir, "abixml-reference")
    if os.path.isdir(abixml_dir) and os.listdir(abixml_dir):
        if os.path.exists(ref_abixml_dir):
            shutil.rmtree(ref_abixml_dir)
        if not os.path.exists(ref_abixml_arch_parent):
            bb.utils.mkdirhier(ref_abixml_arch_parent)
        shutil.copytree(abixml_dir, ref_abixml_dir)
    ref_headers_dir = os.path.join(dest_basedir, "headers")
    ref_headers_snap = os.path.join(dest_basedir, "headers-reference")
    if os.path.isdir(ref_headers_dir) and os.listdir(ref_headers_dir):
        if os.path.exists(ref_headers_snap):
            shutil.rmtree(ref_headers_snap)
        shutil.copytree(ref_headers_dir, ref_headers_snap)

    if not os.path.exists(abixml_dir):
        bb.utils.mkdirhier(abixml_dir)

    for item in os.listdir(abixml_dir):
        itempath = os.path.join(abixml_dir, item)
        os.unlink(itempath)

    # Ensure abidw is in PATH
    native_bindir = os.path.join(d.getVar("RECIPE_SYSROOT_NATIVE"), "usr", "bin")
    staging_bindir_native = d.getVar("STAGING_BINDIR_NATIVE") or ""
    for bindir in [native_bindir, staging_bindir_native]:
        if bindir and os.path.isdir(bindir) and bindir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = bindir + ":" + os.environ.get("PATH", "")

    kv = d.getVar("KERNEL_VERSION")
    artifact_dir = d.getVar("IMG_DIR")
    ltree = os.path.join(artifact_dir, "usr", "lib", "modules")
    if kv and os.path.isdir(ltree):
        # XXX This vmlinux lookup method is very vague
        ptr = os.path.join(d.getVar("WORKDIR"), "..", "..", d.getVar("PREFERRED_PROVIDER_virtual/kernel"), "*", "*", "vmlinux")
        vmlinux = glob.glob(ptr)[0]
        whitelist = None
        out, out_fn = abicheck.serialize_kernel_artifacts(abixml_dir, ltree, vmlinux, whitelist)
        with open(out_fn, "w") as f:
            f.write(out)
    else:
        headers_dir = os.path.join(d.getVar("D"), d.getVar("includedir").lstrip("/"))
        for out, out_fn in abicheck.serialize_artifacts(abixml_dir, artifact_dir, headers_dir=headers_dir):
            with open(out_fn, "w") as f:
                f.write(out)
        if os.path.isdir(headers_dir):
            stored_headers_dir = os.path.join(dest_basedir, "headers")
            if os.path.exists(stored_headers_dir):
                shutil.rmtree(stored_headers_dir)
            shutil.copytree(headers_dir, stored_headers_dir, symlinks=True, ignore_dangling_symlinks=True)

    t1 = time.monotonic()
    duration_fl = abixml_dir + ".duration"
    bb.note("do_gather_abixml: start={}, end={}, duration={}".format(t0, t1, t1 - t0))
    with open(duration_fl, "w") as f:
        f.write(u"{}".format(t1 - t0))

    # Copy output to sstate staging dir for caching
    sstate_dir = os.path.join(d.getVar("WORKDIR"), "abixml-sstate")
    if os.path.exists(sstate_dir):
        shutil.rmtree(sstate_dir)
    shutil.copytree(dest_basedir, sstate_dir)
}

addtask gather_abixml after do_install before do_package
do_gather_abixml[depends] += "${@ 'libabigail-native:do_populate_sysroot' if d.getVar('ABI_CHECK_SKIP') != '1' and d.getVar('CLASSOVERRIDE') == 'class-target' else ''}"
do_gather_abixml[dirs] = "${WORKDIR}"
do_gather_abixml[sstate-inputdirs] = "${WORKDIR}/abixml-sstate"
do_gather_abixml[sstate-outputdirs] = "${BUILDHISTORY_DIR_PACKAGE}/binaryaudit"

python do_gather_abixml_setscene() {
    sstate_setscene(d)
}
addtask do_gather_abixml_setscene

def package_qa_binary_audit_abixml_compare_to_ref(pn, d, messages=None):
    import glob, os, time
    import oe.qa
    from binaryaudit import abicheck

    # Ensure native sysroot binaries (abidiff, abidw) are in PATH
    native_bindir = os.path.join(d.getVar("RECIPE_SYSROOT_NATIVE"), "usr", "bin")
    # Also check the shared native sysroot components for libabigail-native
    staging_bindir_native = d.getVar("STAGING_BINDIR_NATIVE") or ""
    for bindir in [native_bindir, staging_bindir_native]:
        if bindir and os.path.isdir(bindir) and bindir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = bindir + ":" + os.environ.get("PATH", "")

    t0 = time.monotonic()
    recipe_suppr = d.getVar("WORKDIR") + "/abi*.suppr"
    suppr = glob.glob(recipe_suppr)

    if os.path.isfile(str(d.getVar("BINARY_AUDIT_GLOBAL_SUPPRESSION_FILE"))):
        suppr += [d.getVar("BINARY_AUDIT_GLOBAL_SUPPRESSION_FILE")]
    else:
        bb.debug(1, "No global suppression found")
    bb.debug(1, "SUPPRESSION FILES: {}".format(str(suppr)))

    dest_basedir = binary_audit_get_create_pkg_dest_basedir(d)
    pkg_arch = d.getVar("PACKAGE_ARCH")
    cur_abixml_dir = os.path.join(dest_basedir, "abixml", pkg_arch)
    if not os.path.isdir(cur_abixml_dir):
        bb.debug(1, "No ABI dump found in the current build for '{}' under '{}'".format(pn, cur_abixml_dir))
        return

    ref_basedir = d.getVar("BINARY_AUDIT_REFERENCE_BASEDIR")
    if not ref_basedir or len(ref_basedir) < 1:
        bb.debug(1, "BINARY_AUDIT_REFERENCE_BASEDIR not set, no reference ABI comparison to perform")
        return
    if not os.path.isdir(ref_basedir):
        bb.debug(1, "No binary audit reference ABI found under '{}'".format(ref_basedir))
        return
    bb.note("BINARY_AUDIT_REFERENCE_BASEDIR = \"{}\"".format(ref_basedir))

    cur_abidiff_dir = os.path.join(dest_basedir, "abidiff")
    if not os.path.exists(cur_abidiff_dir):
        bb.utils.mkdirhier(cur_abidiff_dir)

    def _compare_abixml(ref_abixml_dir, ref_headers_dir):
        """Compare current abixml against reference. Returns True if reference was found."""
        if not os.path.isdir(ref_abixml_dir):
            return False
        found = False
        for xml_fn in os.listdir(cur_abixml_dir):
            if not xml_fn.endswith('xml'):
                continue
            ref_xml_fpath = os.path.join(ref_abixml_dir, xml_fn)
            if not os.path.isfile(ref_xml_fpath):
                bb.debug(1, "File '{}' is not present in the reference ABI dump".format(xml_fn))
                continue
            cur_xml_fpath = os.path.join(cur_abixml_dir, xml_fn)
            with open(cur_xml_fpath) as f:
                xml = f.read()
            sn = abicheck.get_soname_from_xml(xml)
            if not sn:
                continue
            found = True
            cur_headers_dir = os.path.join(dest_basedir, "headers")
            try:
                ret, out, cmd = abicheck.compare(ref_xml_fpath, cur_xml_fpath, suppr,
                    headers_dir1=ref_headers_dir, headers_dir2=cur_headers_dir)
            except FileNotFoundError:
                bb.warn("%s: abidiff not found, skipping ABI comparison for %s" % (pn, sn))
                continue
            bb.note("abidiff command: " + " ".join(cmd))
            status_bits = abicheck.diff_get_bits(ret)
            with open(os.path.join(cur_abidiff_dir, os.path.splitext(xml_fn)[0] + ".status"), "w") as f:
                f.write("\n".join(status_bits))
            with open(os.path.join(cur_abidiff_dir, os.path.splitext(xml_fn)[0] + ".out"), "w") as f:
                f.write(out)
            bb.note("Generated abidiff for {} in {}".format(xml_fn, cur_abidiff_dir))
            if abicheck.diff_is_incompatible_change(ret):
                oe.qa.handle_error("abi-changed",
                    "%s: ABI incompatibly changed from reference build for %s, logs: %s" % (pn, sn, out), d)
            elif abicheck.diff_is_change(ret):
                bb.warn("%s: ABI changed (compatible additions) for %s, logs: %s" % (pn, sn, out))
            else:
                bb.note("%s: ABI OK - no incompatible changes for %s" % (pn, sn))
        return found

    ref_found = False
    multimach_target_sys = d.getVar("MULTIMACH_TARGET_SYS")
    for fpath in glob.iglob("{}/packages/{}/{}/binaryaudit".format(ref_basedir, multimach_target_sys, pn)):
        ref_abixml_dir = os.path.join(fpath, "abixml", pkg_arch)
        if os.path.isdir(os.path.join(fpath, "abixml-reference", pkg_arch)):
            ref_abixml_dir = os.path.join(fpath, "abixml-reference", pkg_arch)
        ref_headers_dir = os.path.join(fpath, "headers")
        if os.path.isdir(os.path.join(fpath, "headers-reference")):
            ref_headers_dir = os.path.join(fpath, "headers-reference")
        if _compare_abixml(ref_abixml_dir, ref_headers_dir):
            ref_found = True

    # Fallback: use sstate-cached abixml as reference
    if not ref_found:
        sstate_dir = os.path.join(d.getVar("WORKDIR"), "abixml-sstate")
        ref_found = _compare_abixml(
            os.path.join(sstate_dir, "abixml", pkg_arch),
            os.path.join(sstate_dir, "headers"))

    if not ref_found:
        bb.note("No reference ABI found for '{}' - package may be new in this build".format(pn))

    t1 = time.monotonic()
    duration_fl = cur_abidiff_dir + ".duration"
    bb.note("binary_audit_compare_abixml_to_ref: start={}, end={}, duration={}".format(t0, t1, t1 - t0))
    with open(duration_fl, "w") as f:
        f.write(u"{}".format(t1 - t0))

python __anonymous() {
    bb.utils._context["package_qa_binary_audit_abixml_compare_to_ref"] = package_qa_binary_audit_abixml_compare_to_ref
}

QARECIPETEST[abi-changed] = "package_qa_binary_audit_abixml_compare_to_ref"
WARN_QA:append = " abi-changed"

python do_archive_abixmls() {
    import tarfile, os
    import bb.compress.zstd

    d = e.data
    buildhistory_dir = d.getVar('BUILDHISTORY_DIR')
    packages_dir = os.path.join(buildhistory_dir, 'packages')
    if not os.path.isdir(packages_dir):
        bb.debug(1, "No buildhistory packages dir found at '{}'".format(packages_dir))
        return

    distro = d.getVar('DISTRO') or 'unknown'
    distro_version = d.getVar('DISTRO_VERSION') or 'unknown'
    num_threads = int(d.getVar('BB_NUMBER_THREADS') or 1)
    tar_path = os.path.join(buildhistory_dir, '{}-{}-abixmls.tar.zst'.format(distro, distro_version))
    with bb.compress.zstd.open(tar_path, mode='wb', num_threads=num_threads) as zst_f:
        with tarfile.open(fileobj=zst_f, mode='w|') as tar:
            for root, dirs, files in os.walk(packages_dir):
                if os.path.basename(root) == 'abixml':
                    # abixml/<arch>/ subdirs — walk one level deeper
                    for arch_dir in os.listdir(root):
                        arch_path = os.path.join(root, arch_dir)
                        if not os.path.isdir(arch_path):
                            continue
                        for fn in os.listdir(arch_path):
                            if fn.endswith('.xml'):
                                fpath = os.path.join(arch_path, fn)
                                arcname = os.path.relpath(fpath, buildhistory_dir)
                                tar.add(fpath, arcname=arcname)
                latest = os.path.join(root, '..', '..', 'latest')
                if os.path.isfile(latest):
                    arcname = os.path.relpath(os.path.realpath(latest), buildhistory_dir)
                    tar.add(latest, arcname=arcname)
                if 'binaryaudit/headers' in root:
                    for fn in files:
                        fpath = os.path.join(root, fn)
                        arcname = os.path.relpath(fpath, buildhistory_dir)
                        tar.add(fpath, arcname=arcname)
    bb.note("Archived abixmls to '{}'".format(tar_path))
}

addhandler do_archive_abixmls
do_archive_abixmls[eventmask] = "bb.event.BuildCompleted"
