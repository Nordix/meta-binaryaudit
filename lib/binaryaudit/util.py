import os
import sys
import logging

this = sys.modules[__name__]
this.logger = None
this.note = None
this.warn = None
this.error = None
this.fatal = None
this.debug = None


class logger_wrapper:
    def __init__(self, name="binaryaudit"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.WARN)

    def note(self, *args):
        self.logger.info("".join(args))

    def warn(self, *args):
        self.logger.warning("".join(args))

    def error(self, *args):
        self.logger.error("".join(args))

    def fatal(self, *args):
        self.logger.critical("".join(args))

    def debug(self, *args):
        import inspect
        frameinfo = inspect.getouterframes(inspect.currentframe())
        (frame, source, lineno, func, lines, index) = frameinfo[1]
        caller_log = "%s:%s::" % (func, lineno)
        self.logger.debug(caller_log + "".join(args))

    def setLevel(self, level):
        self.logger.setLevel(level)


def _note(*args):
    this.logger.note("".join(args))


def _warn(*args):
    this.logger.warn("".join(args))


def _error(*args):
    this.logger.error("".join(args))


def _fatal(*args):
    this.logger.fatal("".join(args))


def _debug(*args):
    this.logger.debug("".join(args))


def create_logger(name="binaryaudit"):
    logger = logger_wrapper(name)
    return logger


def setup_log(name="binaryaudit"):
    if None is this.logger:
        logging.basicConfig()
        this.logger = create_logger(name)
        this.debug = _debug
        this.note = _note
        this.warn = _warn
        this.error = _error
        this.fatal = _fatal


# TODO perhaps set the exact level instead of just up level to DEBUG
def set_verbosity(v):
    level = logging.WARN
    if v:
        # NOTE this throws together both INFO and DEBUG level which seems
        #      fine fornow. To consider might be using -v repetitions to set
        #      the exact log level
        level = logging.DEBUG

    this.logger.setLevel(level)
    # Set same level on the root logger, if unconfigured
    if 0 == logging.getLogger().getEffectiveLevel():
        logging.getLogger().setLevel(level)


def create_path_to_xml(sn, adir, fn):
    ''' Returns the path through adir to an xml file given its filename or soname
    Parameters:
        sn (str): soname generated from xml file
        adir (str): path to abixml directory
        fn (str): filename
    '''
    if len(sn) > 0:
        # XXX This won't handle multiple soname within the same
        #     recipe. However it's half as bad as with multiple
        #     library versions recipe names need to be different.
        sn_split = sn.split(".")

        if 1 == len(sn_split):
            out_fn = os.path.join(adir, sn)
        else:
            nl = []
            for p in sn_split:
                nl.append(p)
                if "so" == p:
                    break
            nl.append("xml")
            out_fn = os.path.join(adir, ".".join(nl))

    else:
        out_fn = os.path.join(adir, ".".join([os.path.basename(fn), "xml"]))

    return out_fn


# Add or append to a QA message.
# This helper method was renamed after honister, so we implement our
# own here so that it would work across versions.
def add_message(messages, section, new_msg):
    if section not in messages:
        messages[section] = new_msg
    else:
        messages[section] = messages[section] + "\n" + new_msg
