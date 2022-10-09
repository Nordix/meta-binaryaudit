
import os
import time
import tempfile
import shutil
import tarfile
import glob
from binaryaudit import util
from binaryaudit import abicheck
from binaryaudit.db import VERSION_NOT_AVAILABLE


def retrieve_baseline(db_conn, prod_id):
    ''' Fetch buildhistory baseline data from the db and extract for the further usage.

        Parameters:

        Returns:
            baseline_id (int): Baseline ID from DB.
            baseline_dir (str): Path to the extracted buildhistory baseline directory.
    '''
    baseline_id, baseline_data = db_conn.get_ba_latest_baseline(prod_id)
    if not baseline_id:
        util.error("Couldn't find a matching product ID.")
        return None, None
    util.debug("baseline_id: '{}'\n".format(baseline_id))

    data_fl = tempfile.NamedTemporaryFile(delete=False)
    data_fl.write(baseline_data)
    data_fl.flush()
    data_fl.close()

    # TODO Perhaps use a better random path.
    extractdir = "/tmp/binaryaudit_base"
    if os.path.isdir(extractdir):
        shutil.rmtree(extractdir)
    os.makedirs(extractdir)

    with tarfile.open(data_fl.name, "r:gz") as tgz:
        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(tgz, extractdir)
        tgz.close()
    os.unlink(data_fl.name)
    # Depends on how we pack, but the first sibling named "buildhistory" should be it.
    buildhistory_baseline_dir = None
    for root, dirs, files in os.walk(extractdir):
        if "buildhistory" in dirs:
            buildhistory_baseline_dir = os.path.join(root, "buildhistory")
            break
    if not buildhistory_baseline_dir and not os.path.isdir(buildhistory_baseline_dir):
        util.error("Couldn't setup buildhistory baseline.")

    return baseline_id, buildhistory_baseline_dir


def _get_dump_duration(recipe_binaudit_path):
    ret = .0
    fl = recipe_binaudit_path + "/abixml.duration"
    try:
        with open(fl, "r") as f:
            ret = float(f.read())
            f.close()
    except Exception:
        pass
    return ret


def _get_version_from_buildhistory(d):
    latest_fl = os.path.join(d, "latest")
    version = VERSION_NOT_AVAILABLE
    try:
        with open(latest_fl, "r") as f:
            for ln in f.readlines():
                a = ln.split("=")
                if "PV" == a[0].rstrip().lstrip():
                    version = a[1].rstrip().lstrip()
    except Exception:
        pass
    return version


def recipe_abicheck(recipe_binaudit_path, buildhistory_baseline_dir, bulidhistory_current_dir, suppressions):
    t0 = time.monotonic()
    ret_acc = abicheck.DIFF_OK
    dump_duration = _get_dump_duration(recipe_binaudit_path)

    for cur_xml_fl in glob.glob(recipe_binaudit_path + "/abixml/*.xml", recursive=False):
        with open(cur_xml_fl) as f:
            xml = f.read()
            f.close()

        # Care only about DSO for now
        sn = abicheck.get_soname_from_xml(xml)
        # XXX Handle error cases, eg xml file was garbage, etc.
        if len(sn) > 0:
            ref_xml_fl = cur_xml_fl.replace(bulidhistory_current_dir, buildhistory_baseline_dir)
            if not os.path.isfile(ref_xml_fl):
                continue
            ret, out, cmd = abicheck.compare(ref_xml_fl, cur_xml_fl, suppressions)
            if ret > ret_acc:
                # just get the highest score
                ret_acc = ret

    t1 = time.monotonic()

    new_base = os.path.dirname(recipe_binaudit_path)
    old_base = new_base.replace(bulidhistory_current_dir, buildhistory_baseline_dir)

    item_name = os.path.basename(new_base)

    new_version = _get_version_from_buildhistory(new_base)
    base_version = _get_version_from_buildhistory(old_base)

    # Take into account the time spent for serialization during the build, too.
    exec_time = int(dump_duration + (t1-t0)*1000000)  # usec

    result = abicheck.diff_get_bit(ret_acc)
    if 0 == ret_acc:
        res_details = ""
    else:
        res_details = out

    return item_name, base_version, new_version, exec_time, result, res_details, ret_acc
