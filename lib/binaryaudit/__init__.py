from . import util
try:
    # Reverence Poky
    import bb
    util.debug = bb.debug  # noqa: F821
    util.note = bb.note  # noqa: F821
    util.warn = bb.warn  # noqa: F821
    util.error = bb.error  # noqa: F821
    util.fatal = bb.fatal  # noqa: F821
except BaseException:
    util.setup_log()
