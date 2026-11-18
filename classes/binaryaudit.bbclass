
inherit buildhistory

BUILDHISTORY_PRESERVE += "binaryaudit"

# An older buildhistory dir is used as a comparison baseline for the
# current build. Set me in the local.conf.
BINARY_AUDIT_REFERENCE_BASEDIR ?= "${BUILDHISTORY_DIR}"

BINARY_AUDIT_IMPORTS = "abicheck"

def binary_audit_extend_pythonpath(d):
    import sys, os

    pd = d.getVar("BINARY_AUDIT_LAYERDIR")
    sys.path.insert(0, os.path.join(pd, "lib"))

    for toimport in d.getVar("BINARY_AUDIT_IMPORTS").split():
        toimport = "binaryaudit." + toimport
        imported = __import__(toimport)
        #bb.utils._context[toimport] = imported
        __builtins__[toimport] = imported

    return ""

BINARY_AUDIT_IMPORTED := "${@binary_audit_extend_pythonpath(d)}"

def binary_audit_get_create_pkg_dest_basedir(d):
    dest_basedir = d.getVar('BUILDHISTORY_DIR_PACKAGE')
    if not os.path.exists(dest_basedir):
        bb.utils.mkdirhier(dest_basedir)
    dest_basedir = os.path.join(dest_basedir, "binaryaudit")
    if not os.path.exists(dest_basedir):
        bb.utils.mkdirhier(dest_basedir)
    return dest_basedir

