"""
advanced_logger: advanced, flexible logging for scripts, functions and class methods.

Main entry points (Python 3.10+):

- :class:`AdvancedLogger`: a ``logging.Logger`` subclass with colored, aligned console output,
  an optional log file, and setters for every formatting option.
- :func:`make_timestamped_logger`: an ``AdvancedLogger`` whose log file lands in
  ``<parent_dir>/logs/<module path>/<timestamp>/<module>.log``.
- :func:`clean_old_logs`: deletes those timestamped log directories once they are old enough.
- :func:`log_funcall`: decorator that logs calls of (and errors in) module-level functions.
- :class:`MethodLogger`: decorator that does the same for instance methods.
- :class:`Verbosity`: ``IntEnum`` of verbosity levels for functions that take a ``verbose`` argument.

A Python 2.7 port of the same API lives in :mod:`advanced_logger.adv_logging_py2`. This file is
kept Python-2-compatible so that ``from advanced_logger.adv_logging_py2 import ...`` keeps working
when the package source is on ``PYTHONPATH`` of a Python 2.7 interpreter.
"""

import sys

__version__ = "0.1.0"

if sys.version_info >= (3, 10):
    from .adv_logging import (  # noqa: F401
        COLORS,
        LOG_LEVELS,
        MAX_FIELD_WIDTH,
        AdvancedLogger,
        ConsoleFormatter,
        FileFormatter,
        MethodLogger,
        clean_old_logs,
        ensure_dir,
        ensure_parent,
        get_logger,
        log_funcall,
        log_method_call,
        make_timestamped_logger,
    )
    from .verbosity import Verbosity  # noqa: F401

    __all__ = [
        "COLORS",
        "LOG_LEVELS",
        "MAX_FIELD_WIDTH",
        "AdvancedLogger",
        "ConsoleFormatter",
        "FileFormatter",
        "MethodLogger",
        "Verbosity",
        "clean_old_logs",
        "ensure_dir",
        "ensure_parent",
        "get_logger",
        "log_funcall",
        "log_method_call",
        "make_timestamped_logger",
    ]
else:
    # Python 2.7 (or Python 3 older than 3.10): import from advanced_logger.adv_logging_py2
    # explicitly. Nothing is re-exported here, so importing that submodule stays side-effect free.
    __all__ = []
