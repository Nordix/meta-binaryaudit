import json
import os
import subprocess
from binaryaudit import run
from xml.etree import ElementTree
import glob
from binaryaudit import util


def is_elf(fn):
    with open(fn, "rb") as fd:
        exp = b"\177ELF"
        head = fd.read(4)
    return head == exp


def get_soname_from_xml(xml):
    if not xml or not xml.startswith('<'):
        return ""
    try:
        r = ElementTree.fromstring(xml)
        return r.attrib["soname"]
    except (ElementTree.ParseError, AttributeError, KeyError):
        return ""


def _serialize(cmd):
    sout = subprocess.PIPE
    serr = subprocess.STDOUT
    shell = False
    try:
        process = subprocess.Popen(cmd, stdout=sout,
                                   stderr=serr, shell=shell)
        sout, serr = process.communicate()
        out = "".join([out.decode('utf-8') for out in [sout, serr] if out])
    except OSError:
        raise
    return process.returncode, out


def serialize(fn, debug_info_dir=None):
    cmd = ["abidw", "--no-corpus-path", fn]
    if debug_info_dir and os.path.isdir(debug_info_dir):
        cmd += ["--debug-info-dir", debug_info_dir]
    status, out = _serialize(cmd)
    return status, out, cmd


def serialize_kernel_artifacts(abixml_dir, tree, vmlinux=None, whitelist=None):
    cmd = ["abidw", "--no-corpus-path"]
    cmd.extend(["--linux-tree", tree])
    if vmlinux:
        cmd.extend(["--vmlinux", vmlinux])
    if whitelist:
        cmd.extend(["--kmi-whitelist", whitelist])

    util.note(" ".join(cmd))
    ret, out = _serialize(cmd)
    if not 0 == ret:
        util.error(out)
        return out, None
    if not out:
        util.warn("Empty dump output for '{}'".format(tree))
        return None, None

    sn = get_soname_from_xml(out)

    out_fn = util.create_path_to_xml(sn, abixml_dir, tree)

    return out, out_fn


def compare(ref, cur, suppr=[]):
    cmd = ["abidiff"]
    for sup_fn in suppr:
        cmd += ["--suppr", sup_fn]
    cmd += [ref, cur]

    sout = subprocess.PIPE
    serr = subprocess.STDOUT
    shell = False
    try:
        process = subprocess.Popen(cmd, stdout=sout,
                                   stderr=serr, shell=shell)
        sout, serr = process.communicate()
        out = "".join([out.decode('utf-8') for out in [sout, serr] if out])
    except OSError:
        raise
    # return cmd for logging purposes
    return process.returncode, out, cmd


def serialize_artifacts(adir, id, debug_info_dir=None):
    ''' Recursively serialize binary artifacts starting at the given image directory(id), yields serialized output and filename
    Parameters:
        adir (str): path to abixml directory
        id (str): image directory- result of calling d.getVar("IMG_DIR")
        debug_info_dir (str): optional path to directory containing debug info (.debug files)
    '''
    for fn in glob.iglob(id + "/**/**", recursive=True):
        if os.path.isfile(fn) and not os.path.islink(fn):
            is_elf_artifact = False
            try:
                is_elf_artifact = is_elf(fn)
            except Exception as e:
                util.warn(str(e))
            if not is_elf_artifact:
                continue

            # If there's no error, out is the XML representation
            ret, out, cmd = serialize(fn, debug_info_dir)
            util.note(" ".join(cmd))
            if not 0 == ret:
                util.error(out)
                return
            if not out:
                util.warn("Empty dump output for '{}'".format(fn))
                return

            sn = get_soname_from_xml(out)

            out_fn = util.create_path_to_xml(sn, adir, fn)

            yield out, out_fn


DIFF_OK = 0
DIFF_ERROR = 1
DIFF_USAGE_ERROR = 2
DIFF_CHANGE = 4
DIFF_INCOMPATIBLE_CHANGE = 8


def diff_is_ok(c):
    return 0 == c


def diff_is_error(c):
    return (c & 1) == 1


def diff_is_usage_error(c):
    return (c & 2) == 2


def diff_is_change(c):
    return (c & 4) == 4


def diff_is_incompatible_change(c):
    return (c & 8) == 8


def diff_get_bits(c):
    ''' Circle through the return value bits

        Parameters:
            c (int) - Return value to parse.

        Returns:
            Array with the text representations of bits.

    '''
    a = []
    if diff_is_ok(c):
        a.append("OK")
    if diff_is_error(c):
        a.append("ERROR")
    if diff_is_usage_error(c):
        a.append("USAGE_ERROR")
    if diff_is_change(c):
        a.append("CHANGE")
    if diff_is_incompatible_change(c):
        a.append("INCOMPATIBLE_CHANGE")

    if 0 == len(a):
        raise ValueError("Value '{}' can't be interpreted as a libabigail return status.".format(c))

    return a


def diff_get_bit(c):
    ''' Circle through the return value bits.

        Parameters:
            c (int) - Return value to parse.

        Returns:
            The text representation for the most relevant bit.
    '''

    # Order matters.
    if diff_is_ok(c):
        return "OK"
    if diff_is_usage_error(c):
        return "USAGE_ERROR"
    if diff_is_error(c):
        return "ERROR"
    if diff_is_incompatible_change(c):
        return "INCOMPATIBLE_CHANGE"
    if diff_is_change(c):
        return "CHANGE"

    raise ValueError("Value '{}' can't be interpreted as a libabigail return status.".format(c))


def generate_package_json(source_dir, out_filename):
    ''' Gets input directory of RPMs, groups packages based on source RPM, and outputs to JSON file.

        Parameters:
            source_dir (str): The path to the input directory.
            out_filename (str): The name of the output JSON file
    '''
    rpm_dict = {}
    for filename in os.listdir(source_dir):
        f = os.path.join(source_dir, filename)
        if os.path.isfile(f):
            if f.endswith(".rpm"):
                proc, proc_exit_code = run.run_command(["rpm", "-qpi", f], None, subprocess.PIPE)
                grep, grep_exit_code = run.run_command(["grep", "Source RPM"], proc.stdout, subprocess.PIPE)
                source = grep.stdout.read()
                source = source.replace(b"Source RPM  : ", b"")
                source = source.replace(b"\n", b"")
                rpm_dict.setdefault(source.decode('utf-8'), []).append(filename)
    with open(out_filename, "w") as outputFile:
        json.dump(rpm_dict, outputFile, indent=2)
