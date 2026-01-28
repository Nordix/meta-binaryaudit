
inherit binaryaudit
inherit insane

BUILDHISTORY_FEATURES += "abicheck"

DEPENDS:append:class-target = "${@ ' libabigail-native' if d.getVar('ABI_CHECK_SKIP') != '1' else ''}"

IMG_DIR = "${WORKDIR}/image"

python binary_audit_gather_abixml() {
    import glob, os, time
    from binaryaudit import abicheck

    t0 = time.monotonic()

    dest_basedir = binary_audit_get_create_pkg_dest_basedir(d)

    abixml_dir = os.path.join(dest_basedir, "abixml")
    if not os.path.exists(abixml_dir):
        bb.utils.mkdirhier(abixml_dir)

    for item in os.listdir(abixml_dir):
        itempath = os.path.join(abixml_dir, item)
        os.unlink(itempath)

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
            f.close()
    else:
        for out, out_fn in abicheck.serialize_artifacts(abixml_dir, artifact_dir):
            with open(out_fn, "w") as f:
                f.write(out)
                f.close()

    t1 = time.monotonic()
    duration_fl = abixml_dir + ".duration"
    bb.note("binary_audit_gather_abixml: start={}, end={}, duration={}".format(t0, t1, t1 - t0))
    with open(duration_fl, "w") as f:
        f.write(u"{}".format(t1 - t0))
        f.close()
}

# Target binaries are the only interest.
do_install[postfuncs] += "${@ 'binary_audit_gather_abixml' if (d.getVar('CLASSOVERRIDE') == 'class-target' and d.getVar('ABI_CHECK_SKIP') != '1') else ''}"
do_install[vardepsexclude] += "${@ "binary_audit_gather_abixml" if ("class-target" == d.getVar("CLASSOVERRIDE")) else "" }"

QARECIPETEST[abi-changed] = "package_qa_binary_audit_abixml_compare_to_ref"
def package_qa_binary_audit_abixml_compare_to_ref(pn, d, messages=None):
    if messages is None:
        return
    import glob, os, time
    from binaryaudit import util
    from binaryaudit import abicheck

    t0 = time.monotonic()
    
    recipe_suppr = d.getVar("WORKDIR") + "/abi*.suppr"

    suppr = glob.glob(recipe_suppr)

    if os.path.isfile(str(d.getVar("BINARY_AUDIT_GLOBAL_SUPPRESSION_FILE"))):
        suppr += [d.getVar("BINARY_AUDIT_GLOBAL_SUPPRESSION_FILE")]
    else:
        util.note("No global suppression found")
        
    util.note("SUPPRESSION FILES: {}".format(str(suppr)))


    dest_basedir = binary_audit_get_create_pkg_dest_basedir(d)
    cur_abixml_dir = os.path.join(dest_basedir, "abixml")
    if not os.path.isdir(cur_abixml_dir):
        util.note("No ABI dump found in the current build for '{}' under '{}'".format(pn, cur_abixml_dir))
        return

    ref_basedir = d.getVar("BINARY_AUDIT_REFERENCE_BASEDIR")
    if len(ref_basedir) < 1:
        util.note("BINARY_AUDIT_REFERENCE_BASEDIR not set, no reference ABI comparison to perform")
        return
    if not os.path.isdir(ref_basedir):
        util.note("No binary audit reference ABI found under '{}'".format(ref_basedir))
        return
    util.note("BINARY_AUDIT_REFERENCE_BASEDIR = \"{}\"".format(ref_basedir))

    cur_abidiff_dir = os.path.join(dest_basedir, "abidiff")
    if not os.path.exists(cur_abidiff_dir):
        bb.utils.mkdirhier(cur_abidiff_dir)


    for fpath in glob.iglob("{}/packages/*/**/{}/binaryaudit".format(ref_basedir, pn), recursive = True):
        ref_abixml_dir = os.path.join(fpath, "abixml")
        if not os.path.isdir(ref_abixml_dir):
            util.note("No ABI reference found for '{}' under '{}'".format(pn, ref_abixml_dir))
            continue

        # A correct reference history dir for this package is found, proceed
        # to see if there's something to compare
        for xml_fn in os.listdir(cur_abixml_dir):
            if not xml_fn.endswith('xml'):
                continue

            ref_xml_fpath = os.path.join(ref_abixml_dir, xml_fn)
            if not os.path.isfile(ref_xml_fpath):
                util.note("File '{}' is not present in the reference ABI dump".format(xml_fn))
                continue

            cur_xml_fpath = os.path.join(cur_abixml_dir, xml_fn);
            with open(cur_xml_fpath) as f:
                xml = f.read()
                f.close()

            # Care only about DSO for now
            sn = abicheck.get_soname_from_xml(xml)
            # XXX Handle error cases, eg xml file was garbage, etc.
            if len(sn) > 0:
                # XXX Implement suppression handling
                ret, out, cmd = abicheck.compare(ref_xml_fpath, cur_xml_fpath, suppr)

                util.note(" ".join(cmd))

                status_bits = abicheck.diff_get_bits(ret)

                cur_status_fpath = os.path.join(cur_abidiff_dir, ".".join([os.path.splitext(xml_fn)[0], "status"]))
                with open(cur_status_fpath, "w") as f:
                    k = 0
                    while k + 1 < len(status_bits):
                        f.write(status_bits[k] + "\n")
                        k = k + 1
                    f.write(status_bits[k])
                    f.close()
                cur_out_fpath = os.path.join(cur_abidiff_dir, ".".join([os.path.splitext(xml_fn)[0], "out"]))
                with open(cur_out_fpath, "w") as f:
                    f.write(out)
                    f.close()

                if abicheck.diff_is_ok(ret):
                    continue

                #for n in range(8):
                #    bb.note("bit '{}': '{}'".format(n, (ret >> n) & 1))

                status_ln = " ".join(status_bits)
                # XXX Just warn for now if there's anythnig non 0 in the status.
                #     Should be made finer configurable through local.conf.
                util.add_message(messages, 'abi-changed',
                                '%s: ABI changed from reference build, logs: %s'
                                % (pn, out))


    t1 = time.monotonic()
    duration_fl = cur_abidiff_dir + ".duration"
    bb.note("binary_audit_abixml_compare_to_ref: start={}, end={}, duration={}".format(t0, t1, t1 - t0))
    with open(duration_fl, "w") as f:
        f.write(u"{}".format(t1 - t0))
        f.close()

