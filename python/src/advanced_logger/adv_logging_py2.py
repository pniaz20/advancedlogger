# -*- coding: utf-8 -*-
"""
Advanced logging utilities for Python 2.7, which can be used for generating
  time-stamped logs while running programs. This is very useful because:
  - Classes inherit from the `logging.Logger` class, so you can treat them as typical Python loggers.
  - It can use different colors for info, warnings, and errors, making them easy to distinguish.
  - It can report the class or function name being called that generates a line of log,
    so you know exactly which function generated an error or warning.
  - It can include additional flags or strings in every line of the log, so you can be more informative about the
    features of the log being generated.
  - It automatically writes all generated logs into a specifiable log file, to be inspected later.
  - It provides Python decorators for use in modeule-level functions or class methods, so logging of a 
    function/method call is done automatically. Therefore, when a function or method fails, it automatically
    generates logs for the failure, writes them into the log file specified, and if desired, returns a
    default value and skips the function/method. This prevents the need to to use try-except blocks in every
    function/method full of verbose print statements.

NOTE (Py2 port): Functionality that does not exist in Python 2.7 has been omitted,
  namely: static type hints, ``typing``/``ParamSpec``/``Concatenate``, ``os.fspath``/
  ``os.PathLike`` support, and the ``inspect.Signature``-based signature rewriting of the
  decorated wrapper. The call-time logger injection of ``log_funcall`` (both the standalone
  function and the ``AdvancedLogger`` method) IS ported, using ``inspect.getargspec`` for
  signature introspection instead of ``inspect.signature``.
"""

from __future__ import print_function
import logging
import sys
import traceback
from functools import wraps
import warnings
import time
import os
import errno
import inspect
import re
import shutil
from datetime import date, datetime, timedelta

# Custom log level names
LOG_LEVELS = {
    logging.DEBUG: "DBG",
    logging.INFO: "INF",
    logging.WARNING: "WRN",
    logging.ERROR: "ERR",
    logging.CRITICAL: "CRT",
}

# ANSI color codes for the log level in console output
COLORS = {
    "DBG": "\033[90m",  # Gray
    "INF": "\033[92m",  # Green
    "WRN": "\033[93m",  # Yellow
    "ERR": "\033[91m",  # Red
    "CRT": "\033[91m",  # Red
    "RESET": "\033[0m",
}

# Fixed field width for module.function alignment
MAX_FIELD_WIDTH = 40  # Adjust as needed

# Unique sentinel for globals injection/restoration
_GLOBALS_SENTINEL = object()


def ensure_dir(dirpath):
    try:
        os.makedirs(dirpath)
    except OSError as e:
        # It's OK if the directory exists
        if e.errno != errno.EEXIST or not os.path.isdir(dirpath):
            raise

def ensure_parent(filepath):
    parent = os.path.dirname(filepath)
    if parent:
        ensure_dir(parent)


def _log_as(logger, level, func, msg, *args, **kwargs):
    """Log *msg* as if it had been emitted from inside *func*.

    The decorators in this module log on behalf of the function they decorate. A normal
    ``logger.info(...)`` call attributes the record to the code that called the logger, which
    would be the decorator's internal wrapper, so the log header would read
    ``adv_logging_py2.wrapper``. This builds the record from *func*'s own source file, line and
    name instead, so the header reads ``<module of func>.<name of func>``. For an exception, the
    line is the one inside *func* where it was raised.

    Accepts one keyword argument, ``exc_info`` (bool). Loggers without ``makeRecord`` (such as a
    ``logging.LoggerAdapter``) fall back to a normal ``logger.log(...)`` call.
    """
    exc_info = kwargs.pop("exc_info", False)
    if not logger.isEnabledFor(level):
        return
    make_record = getattr(logger, "makeRecord", None)
    if make_record is None:
        logger.log(level, msg, *args, exc_info=exc_info)
        return

    inner = func
    while getattr(inner, "__wrapped__", None) is not None:  # Py3 functools.wraps chains
        inner = inner.__wrapped__
    code = getattr(inner, "__code__", None) or getattr(inner, "func_code", None)
    pathname = code.co_filename if code is not None else "(unknown file)"
    lineno = code.co_firstlineno if code is not None else 0
    ei = sys.exc_info() if exc_info else None
    if ei is not None and code is not None:
        tb = ei[2]
        while tb is not None:
            if tb.tb_frame.f_code is code:
                lineno = tb.tb_lineno
            tb = tb.tb_next

    record = make_record(logger.name, level, pathname, lineno, msg, args, ei, func=func.__name__)
    logger.handle(record)


def _func_globals(func):
    """Return a function's module global namespace (Py2/Py3 compatible attribute name)."""
    return getattr(func, "__globals__", None) or getattr(func, "func_globals")


def _accepts_logger_and_varkw(func, logger_var_name):
    """Inspect *func* and report (declares_logger_param, accepts_var_keyword).

    Uses ``inspect.getargspec`` (Py2) since ``inspect.signature`` does not exist.
    """
    try:
        spec = inspect.getargspec(func)
    except TypeError:
        # Not a pure Python function (e.g. a builtin); assume neither.
        return False, False
    accepts_logger = logger_var_name in spec.args
    accepts_var_keyword = spec.keywords is not None
    return accepts_logger, accepts_var_keyword


class ConsoleFormatter(logging.Formatter):
    """Custom formatter for console output (coloring only the log level)."""
    
    def __init__(self, put_func_name=True, max_width=MAX_FIELD_WIDTH, custom_str="",
                 time_format=None, colored_level=True, colored_log=False):
        super(ConsoleFormatter, self).__init__()
        self.custom_str = custom_str
        self.max_width = max_width
        self.put_func_name = put_func_name
        self.time_format = time_format
        self.colored_level = colored_level
        self.colored_log = colored_log
        if self.colored_log:
            self.colored_level = True
        if not self.colored_level:
            self.colored_log = False
    
    def format(self, record):
        level = LOG_LEVELS.get(record.levelno, "UNK")
        color = COLORS.get(level, COLORS["RESET"])
        if self.time_format is not None and len(self.time_format) > 0:
            timestamp = self.formatTime(record, self.time_format)
        else:
            timestamp = self.formatTime(record)
        if self.put_func_name:
            module_function = "|{}.{}".format(record.module, record.funcName).ljust(self.max_width)[:self.max_width]
        else:
            module_function = ""
        
        # Apply color to log level
        if self.colored_level:
            if self.colored_log and level != "INF":
                level_str = level
            else:
                level_str = "{}{}{}".format(color, level, COLORS['RESET'])
        else:
            level_str = level
        
        cs = "|{}".format(self.custom_str) if len(self.custom_str) > 0 else ""
        log_msg = "[{}{}{}|{}] {}".format(timestamp, module_function, cs, 
                                            level_str, record.getMessage())
        if record.exc_info:
            log_msg += "\n" + self.formatException(record.exc_info)
        if self.colored_log and level != "INF":
            log_msg = "{}{}{}".format(color, log_msg, COLORS['RESET'])
        
        return log_msg


class FileFormatter(logging.Formatter):
    """Formatter for log file output (no colors)."""
    
    def __init__(self, put_func_name=True, max_width=MAX_FIELD_WIDTH, custom_str="", time_format=None):
        super(FileFormatter, self).__init__()
        self.max_width = max_width
        self.custom_str = custom_str
        self.put_func_name = put_func_name
        self.time_format = time_format

    def format(self, record):
        level = LOG_LEVELS.get(record.levelno, "UNK")
        if self.time_format is not None and len(self.time_format) > 0:
            timestamp = self.formatTime(record, self.time_format)
        else:
            timestamp = self.formatTime(record)
        if self.put_func_name:
            module_function = "|{}.{}".format(record.module, record.funcName).ljust(self.max_width)[:self.max_width]
        else:
            module_function = ""
        cs = "|{}".format(self.custom_str) if len(self.custom_str) > 0 else ""
        log_msg = "[{}{}{}|{}] {}".format(timestamp, module_function, cs, level, record.getMessage())
        if record.exc_info:
            log_msg += "\n" + self.formatException(record.exc_info)
        
        return log_msg


def get_logger(name, log_file=None, put_func_name=True, max_width=MAX_FIELD_WIDTH, custom_str="",
               time_format=None, colored_level=True, colored_log=False):
    """Make a custom Python logger with specified attributes.

    Args:
        name (str): The name of the logger, typically __name__.
        log_file (str,optional): Name of the log file to write logs to. Defaults to None.
        put_func_name (bool, optional): Whether to put the function or module name in the log header.
            Defaults to True.
        max_width (int, optional): Maximum field width for writing the function or module name.
            Defaults to MAX_FIELD_WIDTH.
        custom_str (str, optional): Custom string to denote at the end of the log header. Defaults to "".
        time_format (str, optional): Format of the time stamp on the log header.
            Defaults to None (use default format).
        colored_level (bool, optional): Color the log level (INF, WRN, ERR, etc.). Defaults to True.
        colored_log (bool, optional): Make the entire log text colored accordign to the level.
            Defaults to False.

    Returns:
        logging.Logger: A Python logger equipped with the desired specifications.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Log everything

    # Console handler (colored log levels). A StreamHandler that is NOT a FileHandler.
    has_stream_handler = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    )
    if not has_stream_handler:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ConsoleFormatter(put_func_name=put_func_name,
                                                      max_width=max_width, custom_str=custom_str,
                                                      time_format=time_format, colored_level=colored_level,
                                                      colored_log=colored_log))
        logger.addHandler(console_handler)

    # File handler (plain text logs)
    if log_file is not None:
        ensure_parent(log_file)
        abs_log_file = os.path.abspath(log_file)
        has_same_file = any(
            isinstance(h, logging.FileHandler)
            and getattr(h, "baseFilename", None) == abs_log_file
            for h in logger.handlers
        )
        if not has_same_file:
            file_handler = logging.FileHandler(abs_log_file, mode='a')
            file_handler.setFormatter(FileFormatter(put_func_name=put_func_name,
                                                    max_width=max_width, custom_str=custom_str,
                                                    time_format=time_format))
            logger.addHandler(file_handler)

    return logger


# Decorator for logging function calls
def log_funcall(logger=None, default=None, skip=None, verbose=False, logger_var_name="logger"):
    """Decorator for logging function calls, with call-time logger injection.

    The wrapper accepts an optional ``logger`` keyword argument (or the name given by
    ``logger_var_name``) at *call time*.  The resolved logger is also injected into the
    function's module global namespace for the duration of the call, so the function body
    can reference it as a bare name (e.g. ``logger.info(...)``) without declaring it as a
    parameter.

    Logger resolution order (highest priority first):
        1. ``logger`` kwarg passed at call time.
        2. ``logger`` supplied at decoration time.
        3. A fallback logger created with ``get_logger(__name__)``.

    If the function already declares ``logger`` (or ``logger_var_name``) as an explicit
    parameter, the resolved logger is forwarded as that kwarg instead of being injected
    into globals.  If the function accepts ``**kwargs``, ``logger`` is left in kwargs and
    not injected into globals.

    Thread-safety note: the globals-injection path is **not** thread-safe.  For
    concurrent workloads declare ``logger`` explicitly in the function signature.

    Args:
        logger (logging.Logger, optional): Decoration-time fallback logger. Defaults to None.
        default (optional): Default return value when a skipped error occurs. Defaults to None.
        skip (list, optional): List of exception types to catch and skip -- only exceptions that
            are instances of one of these types are caught, logged, and replaced with *default*.
            All other exceptions (and any exception when *skip* is None or empty) propagate
            normally. Defaults to None.
        verbose (bool, optional): Log entry/exit and elapsed time. Defaults to False.
        logger_var_name (str, optional): Name of the logger kwarg/global to inject. Defaults to "logger".

    Returns:
        Callable: A decorator that can be applied to a function.

    Example:
        ```
        my_logger = AdvancedLogger("demo", log_file="demo.log")

        @log_funcall(skip=[ZeroDivisionError], verbose=True)
        def compute(x, y):
            logger.info("computing %s / %s", x, y)  # 'logger' resolved via globals injection
            return x / y

        compute(10, 2, logger=my_logger)   # uses my_logger; logs entry/exit
        compute(10, 0, logger=my_logger)   # ZeroDivisionError caught, returns None
        compute(10, 2)                     # uses fallback logger
        ```
    """
    def decorator(func):
        _func_accepts_logger, _func_has_var_keyword = _accepts_logger_and_varkw(func, logger_var_name)
        _inject_via_globals = (not _func_accepts_logger) and (not _func_has_var_keyword)

        @wraps(func)
        def wrapper(*args, **kwargs):
            if _inject_via_globals:
                call_time_logger = kwargs.pop(logger_var_name, None)
            else:
                call_time_logger = kwargs.get(logger_var_name)

            active_logger = call_time_logger or logger or get_logger(__name__)

            func_globals = _func_globals(func)
            orig_global = _GLOBALS_SENTINEL
            if _inject_via_globals:
                orig_global = func_globals.get(logger_var_name, _GLOBALS_SENTINEL)
                func_globals[logger_var_name] = active_logger
            elif _func_accepts_logger and logger_var_name not in kwargs:
                kwargs[logger_var_name] = active_logger

            try:
                if verbose:
                    _log_as(active_logger, logging.INFO, func, "Calling %s ...", func.__name__)
                t1 = time.time()
                result = func(*args, **kwargs)
                t2 = time.time()
                if verbose:
                    _log_as(active_logger, logging.INFO, func,
                            "Finished %s in %.4f seconds.", func.__name__, t2 - t1)
                return result
            except Exception as e:
                _log_as(active_logger, logging.ERROR, func,
                        "Error in %s: %s", func.__name__, str(e), exc_info=True)
                if skip and isinstance(e, tuple(skip)):
                    _log_as(active_logger, logging.WARNING, func,
                            "Skipping %s (%s) due to error.", func.__name__, type(e).__name__)
                    return default
                raise
            finally:
                if _inject_via_globals:
                    if orig_global is _GLOBALS_SENTINEL:
                        func_globals.pop(logger_var_name, None)
                    else:
                        func_globals[logger_var_name] = orig_global

        return wrapper

    return decorator


def log_method_call(default=None, skip=None, verbose=False, loggerVarName="logger"):
    """Decorator for logging instance method calls, with options for default return value and skipping on error.
    This decorator can be used for logging instance methods of classes. Therefore, you can report running the method, and report any errors in a log and write the log into a file, without needing to write try-except blocks in the method body.

    Args:
        default (optional): Default return value of the method. Defaults to None.
            This is used in case there are errors and you want to just return a default value and skip the errors.
        skip (list, optional): List of exception types to catch and skip. Only exceptions that are
            instances of one of these types are caught, logged, and replaced with *default*. All other
            exceptions (and any exception when *skip* is None or empty) propagate normally. Defaults to None.
        verbose (bool, optional): Whether to explicitly log the method call and time the method. Defaults to False.
        loggerVarName (str, optional): The name of the logger variable in the class instance. Defaults to "logger".
             The decorator will look for a logger with this name in the class instance to log the method calls and errors. If not found, it will not log anything but will still handle exceptions and default return values according to the skip and default parameters.

    Returns:
        Callable: A decorator that can be applied to an instance method to enable the described logging behavior.
    """
    warnings.warn("log_method_call is deprecated; use MethodLogger instead.", DeprecationWarning)
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            logger = getattr(self, loggerVarName, None)
            try:
                if verbose and logger is not None:
                    _log_as(logger, logging.INFO, func, "Calling %s ...", func.__name__)
                t1 = time.time()
                result = func(self, *args, **kwargs)
                t2 = time.time()
                if verbose and logger is not None:
                    _log_as(logger, logging.INFO, func,
                            "Finished %s in %.4f seconds.", func.__name__, t2 - t1)
                return result
            except Exception as e:
                if logger is not None:
                    _log_as(logger, logging.ERROR, func,
                            "Error in %s: %s", func.__name__, str(e), exc_info=True)
                if skip and isinstance(e, tuple(skip)):
                    if logger is not None:
                        _log_as(logger, logging.WARNING, func,
                                "Skipping %s (%s) due to error.", func.__name__, type(e).__name__)
                    return default
                raise

        return wrapper

    return decorator



class AdvancedLogger(logging.Logger):
    """
    A Python `logging.Logger` subclass that adds custom formatters and decorators.
    This enables logging function calls implicitly without having to write try-except blocks in the 
    function/method body, and also provides more informative and colorful logs.
    """

    def __init__(self, name, log_file=None, put_func_name=True, max_width=MAX_FIELD_WIDTH, custom_str="",
                 time_format=None, colored_level=True, colored_log=False):
        """
        Initializes the AdvancedLogger class.
        This is a Logger subclass that:
        - automatically attaches a colored customizable console handler (ConsoleFormatter)
        - optionally attaches a customizable FileHandler (FileFormatter)
        - provides a decorator `@log_funcall(...)` to automatically catch-and-log exceptions
          in module-level (standalone) functions.
        - provides methods for changing all the attributes: log file, colored logs and levels, time format,
          function name in log header, custom string in log header, etc.
        
        Args:
            name (str): The name of the logger, typically __name__.
            log_file (str, optional): Path to the log file to write the logs in. Defaults to None.
                If it's None, then logs will not be written to a file, but only printed in the console.
            put_func_name (bool, optional): _description_. Defaults to True.
            max_width (int, optional): Maximum field width for writing the function or module name 
                in the log header. Defaults to MAX_FIELD_WIDTH.
            custom_str (str, optional): Custom string to denote at the end of the log header. Defaults to "".
            time_format (str, optional): Format of the time stamp on the log header.
                Defaults to None (use default format).
            colored_level (bool, optional): Whether to color the log level (INF, WRN, ERR, etc.). Defaults to True.
            colored_log (bool, optional): Whether to make the entire log text colored according to the level. 
                Defaults to False.
        """
        # Initialize the base Logger
        super(AdvancedLogger, self).__init__(name, level=logging.DEBUG)

        self.name = name
        self.log_file = log_file
        self.log_dir = None if log_file is None else os.path.dirname(log_file)
        self.max_width = max_width
        self.custom_str = custom_str
        self.put_func_name = put_func_name
        self.time_format = time_format
        self.colored_level = colored_level
        self.colored_log = colored_log
        
        # Create & add a StreamHandler (console) with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(ConsoleFormatter(put_func_name=put_func_name,
                                                      max_width=max_width, custom_str=custom_str,
                                                      time_format=time_format, colored_level=colored_level,
                                                      colored_log=colored_log))
        self.addHandler(console_handler)

        # If a log_file path is given, create & add a FileHandler
        if log_file is not None:
            ensure_parent(log_file)
            file_handler = logging.FileHandler(log_file, mode="a")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(FileFormatter(put_func_name=put_func_name,
                                                    max_width=max_width, custom_str=custom_str,
                                                    time_format=time_format))
            self.addHandler(file_handler)
    
    def reset_formatters(self):
        """
        Reset the formatters of all handlers to reflect current settings.
        """
        for h in self.handlers:
            if isinstance(h, logging.FileHandler):
                h.setFormatter(FileFormatter(put_func_name=self.put_func_name,
                                             max_width=self.max_width, custom_str=self.custom_str,
                                             time_format=self.time_format))
            elif isinstance(h, logging.StreamHandler):
                h.setFormatter(ConsoleFormatter(put_func_name=self.put_func_name,
                                                max_width=self.max_width, custom_str=self.custom_str,
                                                time_format=self.time_format, colored_level=self.colored_level,
                                                colored_log=self.colored_log))
                
    def reset_defaults(self):
        """
        Reset all settings to their default values.
        """
        self.put_func_name = True
        self.max_width = MAX_FIELD_WIDTH
        self.custom_str = ""
        self.time_format = None
        self.colored_level = True
        self.colored_log = False
        self.reset_formatters()
                
                
    def set_file(self, log_file):
        """
        Set the log file for this logger.
        """
        # Avoid adding duplicates: remove existing FileHandler(s) first
        for h in list(self.handlers):
            if isinstance(h, logging.FileHandler):
                self.removeHandler(h)
                h.close()
        ensure_parent(log_file)
        fh = logging.FileHandler(log_file, mode="a")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(FileFormatter(put_func_name=self.put_func_name,
                                      max_width=self.max_width, custom_str=self.custom_str,
                                      time_format=self.time_format))
        self.addHandler(fh)
        self.log_file = log_file
        self.log_dir = os.path.dirname(log_file)
    
    
    def set_custom_str(self, custom_str):
        """
        Set the custom string to include in log messages.
        """
        self.custom_str = custom_str
        self.reset_formatters()
    

    def set_put_func_name(self, put_func_name):
        """
        Set the boolean describing whether to also put the name of the module/function in the log.
        """
        self.put_func_name = put_func_name
        self.reset_formatters()
    
    
    def set_max_width(self, max_width):
        """
        Set the maximum width for the module.function field in the log.
        """
        self.max_width = max_width
        self.reset_formatters()
    
    
    def set_time_format(self, time_format):
        """
        Set the time format for timestamps in the log.
        """
        self.time_format = time_format
        self.reset_formatters()
    
    def set_coloring(self, colored_level=True, colored_log=False):
        """
        Set the coloring options for console log output.
        """
        self.colored_level = colored_level
        self.colored_log = colored_log
        self.reset_formatters()

    
    def log_funcall(self, default=None, skip=None, verbose=False, logger_var_name="logger"):
        """Decorator for logging function calls, with call-time logger injection.
        Behaves identically to the module-level :func:`log_funcall`, but uses *self* as
        the decoration-time fallback logger.

        Args:
            default (optional): Default return value when a skipped error occurs. Defaults to None.
            skip (list, optional): List of exception types to catch and skip. Only exceptions that
                are instances of one of these types are caught, logged, and replaced with *default*.
                All other exceptions (and any exception when *skip* is None or empty) propagate
                normally. Defaults to None.
            verbose (bool, optional): Log entry/exit and elapsed time. Defaults to False.
            logger_var_name (str, optional): Name of the logger kwarg/global to inject. Defaults to "logger".

        Returns:
            Callable: A decorator that can be applied to a function.
        """

        def decorator(func):
            _func_accepts_logger, _func_has_var_keyword = _accepts_logger_and_varkw(func, logger_var_name)
            _inject_via_globals = (not _func_accepts_logger) and (not _func_has_var_keyword)

            @wraps(func)
            def wrapper(*args, **kwargs):
                if _inject_via_globals:
                    call_time_logger = kwargs.pop(logger_var_name, None)
                else:
                    call_time_logger = kwargs.get(logger_var_name)

                active_logger = call_time_logger or self

                func_globals = _func_globals(func)
                orig_global = _GLOBALS_SENTINEL
                if _inject_via_globals:
                    orig_global = func_globals.get(logger_var_name, _GLOBALS_SENTINEL)
                    func_globals[logger_var_name] = active_logger
                elif _func_accepts_logger and logger_var_name not in kwargs:
                    kwargs[logger_var_name] = active_logger

                try:
                    if verbose:
                        _log_as(active_logger, logging.INFO, func, "Calling %r ...", func.__name__)
                    t1 = time.time()
                    result = func(*args, **kwargs)
                    t2 = time.time()
                    if verbose:
                        _log_as(active_logger, logging.INFO, func,
                                "Finished %r in %.4f seconds.", func.__name__, t2 - t1)
                    return result
                except Exception as e:
                    _log_as(active_logger, logging.ERROR, func,
                            "Error in %r: %s", func.__name__, str(e), exc_info=True)
                    if skip and isinstance(e, tuple(skip)):
                        _log_as(active_logger, logging.WARNING, func,
                                "Skipping %r (%s) due to error.", func.__name__, type(e).__name__)
                        return default
                    raise
                finally:
                    if _inject_via_globals:
                        if orig_global is _GLOBALS_SENTINEL:
                            func_globals.pop(logger_var_name, None)
                        else:
                            func_globals[logger_var_name] = orig_global

            return wrapper

        return decorator



class MethodLogger(object):
    """
    A class-based decorator for logging instance method calls, with options for default return 
    value and skipping on error.
    """
    def __init__(self, logger=None, default=None, skip=None, verbose=False, loggerVarName="logger"):
        """Initializes the MethodLogger decorator.
        This class can be used as a decorator for instance methods of classes. Therefore, you can report running the method, and report any errors in a log and write the log into a file, without needing to write try-except blocks in the method body.

        Args:
            logger (logging.Logger, optional): External Python logger to use, if any is provided. 
                Defaults to None, in which case the decorator will look for a logger with the name specified by loggerVarName in the class instance. If no logger is found, it will not log anything but will still handle exceptions and default return values according to the skip and default parameters.
            default (Any, optional): Default return value of the method. Defaults to None.
                This is used in case there are errors and you want to just return a default value and skip the errors.
            skip (list, optional): List of exception types to catch and skip. Only exceptions that are
                instances of one of these types are caught, logged, and replaced with *default*. All other
                exceptions (and any exception when *skip* is None or empty) propagate normally. Defaults to None.
            verbose (bool, optional): Whether to explicitly log the method call and time the method. Defaults to False.
            loggerVarName (str, optional): The name of the logger variable in the class instance. Defaults to "logger".
                The decorator will look for a logger with this name in the class instance to log the method calls and errors. If not found, it will not log anything but will still handle exceptions and default return values according to the skip and default parameters.
        """
        self._logger = logger
        self.default = default
        self.skip = skip
        self.verbose = verbose
        self.loggerVarName = loggerVarName

    def __call__(self, func):
        @wraps(func)
        def wrapped(obj, *args, **kwargs):
            logger = self._logger or getattr(obj, self.loggerVarName, None)

            try:
                if self.verbose and logger is not None:
                    _log_as(logger, logging.INFO, func, "Calling %s", func.__name__)
                t1 = time.time()
                result = func(obj, *args, **kwargs)
                t2 = time.time()
                if self.verbose and logger is not None:
                    _log_as(logger, logging.INFO, func,
                            "Finished %s in %.4f seconds", func.__name__, t2 - t1)
                return result

            except Exception as e:
                if logger is not None:
                    _log_as(logger, logging.ERROR, func,
                            "Error in %s: %s", func.__name__, e, exc_info=True)
                if self.skip and isinstance(e, tuple(self.skip)):
                    if logger is not None:
                        _log_as(logger, logging.WARNING, func,
                                "Skipping %s (%s) due to error.", func.__name__, type(e).__name__)
                    return self.default
                raise
        return wrapped


def make_timestamped_logger(name, parent_dir, format="%Y%m%d_%H%M%S", **kwargs):
    """Make a timestamped AdvancedLogger with a log file in a default log directory.
    This function creates an AdvancedLogger with a log file in a default log directory of the form:
    `parent_dir/logs/<rel_path>/<timestamp>/basename.log`, where `<rel_path>` is derived from the
    dotted logger name with its top-level package stripped, and `<timestamp>` is generated according
    to the provided format. For example, a logger named `utamp.pipeline.base.afford` produces
    `parent_dir/logs/base/afford/<timestamp>/afford.log`. This is useful for easily generating
    time-stamped logs without needing to specify the log file path every time.

    Args:
        name (str): The name of the logger, typically __name__.
        parent_dir (str): The parent directory under which the log directory will be created. The
            log file will be created in `parent_dir/logs/<rel_path>/<timestamp>/basename.log`.
        format (str, optional): The format of the timestamp to be generated for the log directory.
            Defaults to "%Y%m%d_%H%M%S".
        **kwargs: Additional keyword arguments to be passed to the AdvancedLogger constructor.

    Returns:
        AdvancedLogger: An instance of AdvancedLogger with the log file set to the default path 
            with a timestamped directory.
    """
    timestamp = time.strftime(format)
    parts = name.split(".")[1:] or [name]
    basename = parts[-1]
    default_log_dir = os.path.join(parent_dir, "logs", *(parts + [str(timestamp)]))
    default_log_file = os.path.join(default_log_dir, "{}.log".format(basename))
    return AdvancedLogger(name, log_file=default_log_file, **kwargs)


# Relative-time units accepted in strings like "10 days ago", "3 weeks", "48h".
_REL_TIME_UNITS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1, "s": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60, "m": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600, "h": 3600,
    "day": 86400, "days": 86400, "d": 86400,
    "week": 604800, "weeks": 604800, "wk": 604800, "wks": 604800, "w": 604800,
}
_REL_TIME_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s*(?:ago)?\s*$")


def _coerce_cutoff(older_than, fmt):
    """Resolve *older_than* into an absolute cutoff ``datetime``.

    Accepts:
        - ``None``                 -> 10 days before now (the default).
        - ``datetime``             -> used as-is.
        - ``date``                 -> midnight of that date.
        - ``int`` / ``float``      -> that many days before now.
        - ``str``                  -> either a timestamp matching *fmt* (e.g. "20260101_000000"),
                                      or a relative phrase such as "10 days ago", "3 weeks", "48h".
    """
    if older_than is None:
        return datetime.now() - timedelta(days=10)
    if isinstance(older_than, datetime):
        return older_than
    if isinstance(older_than, date):
        return datetime(older_than.year, older_than.month, older_than.day)
    if isinstance(older_than, bool):  # guard: bool is a subclass of int
        raise TypeError("older_than may not be a bool")
    if isinstance(older_than, (int, float)):
        return datetime.now() - timedelta(days=float(older_than))
    if isinstance(older_than, str):
        s = older_than.strip()
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
        match = _REL_TIME_RE.match(s)
        if match:
            qty = float(match.group(1))
            unit = match.group(2).lower()
            if unit in _REL_TIME_UNITS:
                return datetime.now() - timedelta(seconds=qty * _REL_TIME_UNITS[unit])
        raise ValueError(
            "Could not interpret older_than={!r}; expected a timestamp matching "
            "{!r} or a phrase like '10 days ago', '3 weeks', '48h'.".format(older_than, fmt)
        )
    raise TypeError(
        "older_than must be a datetime, date, int/float (days), str, or None; "
        "got {}.".format(type(older_than).__name__)
    )


def clean_old_logs(parent_dir, older_than=None, fmt="%Y%m%d_%H%M%S",
                   use_mtime_fallback=True, prune_empty=True, dry_run=False):
    """Delete timestamped log chains under ``parent_dir/logs`` that are older than a cutoff.

    This is the cleanup counterpart to :func:`make_timestamped_logger`. That function lays out
    logs as ``parent_dir/logs/<rel_path>/<timestamp>/basename.log``, so every run of every module
    spawns a fresh ``<timestamp>`` directory. Over time these accumulate. This function walks the
    tree, identifies the ``<timestamp>`` leaf directories (those whose name parses against *fmt*),
    and removes -- recursively -- any whose encoded time is strictly older than the cutoff. Because
    it keys off the whole timestamp directory, the entire chain is deleted, not just the ``.log``
    files inside it. Empty parent directories left behind are then pruned, stopping at the
    ``logs`` root itself.

    Args:
        parent_dir (str): The same ``parent_dir`` passed to :func:`make_timestamped_logger`;
            cleanup happens under ``parent_dir/logs``.
        older_than (datetime | date | int | float | str | None, optional): The cutoff. Anything
            older than this is deleted. May be given as:
            an absolute ``datetime`` or ``date``; a number meaning "that many days ago"; or a
            string -- either an absolute timestamp matching *fmt*, or a relative phrase such as
            "10 days ago", "3 weeks", "48h". Defaults to None, meaning 10 days ago.
        fmt (str, optional): The timestamp format used for the ``<timestamp>`` directory names.
            Must match the ``format`` used in :func:`make_timestamped_logger`. Defaults to
            "%Y%m%d_%H%M%S".
        use_mtime_fallback (bool, optional): If a directory's name does not parse as a timestamp
            but it directly contains ``.log`` files (or is otherwise a leaf), fall back to the
            directory's filesystem modification time to decide whether it is old. Defaults to True.
        prune_empty (bool, optional): After deletion, remove directories that have become empty,
            up to but not including the ``logs`` root. Defaults to True.
        dry_run (bool, optional): If True, nothing is deleted; the function only returns the list
            of directories that *would* be removed. Defaults to False.

    Returns:
        list: Absolute paths of the timestamp directories that were deleted (or, under *dry_run*,
            that would be deleted).

    Example:
        ```
        # Remove every log chain older than 10 days (the default):
        clean_old_logs("/path/to/project")

        # Preview what a 2-week cleanup would remove, without deleting:
        to_delete = clean_old_logs("/path/to/project", older_than="2 weeks ago", dry_run=True)

        # Delete everything logged before an explicit date:
        from datetime import datetime
        clean_old_logs("/path/to/project", older_than=datetime(2026, 1, 1))
        ```
    """
    cutoff = _coerce_cutoff(older_than, fmt)
    logs_root = os.path.join(parent_dir, "logs")
    deleted = []

    if not os.path.isdir(logs_root):
        return deleted

    logs_root_abs = os.path.abspath(logs_root)

    # First pass (bottom-up): delete timestamp leaf directories older than the cutoff.
    for dirpath, dirnames, filenames in os.walk(logs_root, topdown=False):
        if os.path.abspath(dirpath) == logs_root_abs:
            continue

        name = os.path.basename(dirpath)
        try:
            dir_time = datetime.strptime(name, fmt)
        except ValueError:
            dir_time = None

        if dir_time is None:
            # Not a timestamp directory. Optionally treat a leaf holding .log files as old
            # based on its filesystem mtime.
            if use_mtime_fallback and not dirnames and filenames:
                if any(f.endswith(".log") for f in filenames):
                    mtime = datetime.fromtimestamp(os.path.getmtime(dirpath))
                    if mtime < cutoff:
                        deleted.append(os.path.abspath(dirpath))
                        if not dry_run:
                            shutil.rmtree(dirpath, ignore_errors=True)
            continue

        if dir_time < cutoff:
            deleted.append(os.path.abspath(dirpath))
            if not dry_run:
                shutil.rmtree(dirpath, ignore_errors=True)

    # Second pass (bottom-up): prune directories that are now empty, never touching logs_root.
    if prune_empty and not dry_run:
        for dirpath, dirnames, filenames in os.walk(logs_root, topdown=False):
            if os.path.abspath(dirpath) == logs_root_abs:
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except OSError:
                pass

    return deleted


def test_my_logger(logger):
    logger.debug("This is a debug message.")
    logger.info("This is an info message.")
    logger.warning("This is a warning message.")
    logger.error("This is an error message.")
    logger.critical("This is a critical message.")


if __name__ == "__main__":

    test_log_file1 = os.path.join(os.path.dirname(__file__), "test_logging", "AdvancedLogger_test1.log")
    test_log_file2 = os.path.join(os.path.dirname(__file__), "test_logging", "AdvancedLogger_test2.log")

    print("\nInstantiating AdvancedLogger and testing it ...")
    my_logger = AdvancedLogger("test_logger", log_file=test_log_file1, put_func_name=False)
    test_my_logger(my_logger)

    print("\nTesting set_func_name ...")
    my_logger.set_put_func_name(True)
    test_my_logger(my_logger)

    print("\nTesting set_max_width ...")
    my_logger.set_max_width(50)
    test_my_logger(my_logger)
    my_logger.reset_defaults()

    print("\nTesting set_time_format ...")
    my_logger.set_time_format("%Y-%m-%d %H:%M:%S")
    test_my_logger(my_logger)
    my_logger.reset_defaults()

    print("\nTesting set_coloring ...")
    print("All colored:")
    my_logger.set_coloring(colored_level=False, colored_log=True)
    test_my_logger(my_logger)
    print("No color:")
    my_logger.set_coloring(colored_level=False, colored_log=False)
    test_my_logger(my_logger)
    my_logger.reset_defaults()

    print("\nTesting set_custom_str ...")
    my_logger.set_custom_str("TEST1")
    test_my_logger(my_logger)
    my_logger.reset_defaults()

    print("\nSetting up logger for test_log_file2 ...")
    my_logger.set_file(test_log_file2)
    my_logger.set_coloring(colored_level=True, colored_log=False)
    my_logger.info("This message goes to AdvancedLogger_test2.log as well.")
    my_logger.debug("This is a debug message in AdvancedLogger_test2.log.")
    my_logger.warning("This is a warning message in AdvancedLogger_test2.log.")
    my_logger.error("This is an error message in AdvancedLogger_test2.log.")
    my_logger.critical("This is a critical message in AdvancedLogger_test2.log.")

    print("\nTesting the AdvancedLogger.log_funcall decorator with no explicit parameters or arguments ...")
    @my_logger.log_funcall(default="default value", skip=[ZeroDivisionError], verbose=False)
    def might_fail(x, y):
        logger.debug("Logger inside function definition")
        return x/y
    good_result = might_fail(10, 2)  # Should succeed
    print("Good result: {}".format(good_result))
    bad_result = might_fail(10, 0)  # Should log error and return default value
    print("Bad result: {}".format(bad_result))  # Should print "default value"

    print("\nTesting the standalone log_funcall decorator WITHOUT explicit parameter ...")
    @log_funcall(logger=my_logger, default="default value", skip=[ZeroDivisionError], verbose=True)
    def might_fail_standalone_no_param(x, y):
        logger.debug("Logger inside function definition")
        return x / y
    print("\nCalling function WITHOUT logger argument ...")
    good_result = might_fail_standalone_no_param(10, 2)  # Should succeed
    print("Good result: {}".format(good_result))
    bad_result = might_fail_standalone_no_param(10, 0)  # Should log error and return default value
    print("Bad result: {}".format(bad_result))  # Should print "default value"
    print("\nCalling function WITH logger argument ...")
    good_result = might_fail_standalone_no_param(10, 2, logger=my_logger)  # Should succeed
    print("Good result: {}".format(good_result))
    bad_result = might_fail_standalone_no_param(10, 0, logger=my_logger)  # Should log error and return default value
    print("Bad result: {}".format(bad_result))  # Should print "default value"

    print("\nTesting the standalone log_funcall decorator WITH explicit parameter ...")
    @log_funcall(logger=my_logger, default="default value", skip=[ZeroDivisionError], verbose=True)
    def might_fail_standalone_with_param(x, y, logger=None):
        logger.debug("Logger inside function definition")
        return x / y
    print("\nCalling function WITHOUT logger argument ...")
    good_result = might_fail_standalone_with_param(10, 2)  # Should succeed
    print("Good result: {}".format(good_result))
    bad_result = might_fail_standalone_with_param(10, 0)  # Should log error and return default value
    print("Bad result: {}".format(bad_result))  # Should print "default value"
    print("\nCalling function WITH logger argument ...")
    good_result = might_fail_standalone_with_param(10, 2, logger=my_logger)  # Should succeed
    print("Good result: {}".format(good_result))
    bad_result = might_fail_standalone_with_param(10, 0, logger=my_logger)  # Should log error and return default value
    print("Bad result: {}".format(bad_result))  # Should print "default value"

    print("\nTesting the standalone log_method_call decorator ...")
    class Foo:
        def __init__(self, logger):
            self.logger = logger

        @log_method_call(default="default value", skip=[ZeroDivisionError], verbose=True, loggerVarName="logger")
        def might_fail(self, x, y):
            self.logger.debug("Logger inside function definition")
            return x / y

    foo = Foo(my_logger)
    good_result = foo.might_fail(10, 2)  # Should succeed
    print("Good result: {}".format(good_result))
    bad_result = foo.might_fail(10, 0)  # Should log error and return default value
    print("Bad result: {}".format(bad_result))  # Should print "default value"

    print("\nTesting the MethodLogger class without specific logger ...")
    class Bar:
        def __init__(self, logger):
            self.logger = logger

        @MethodLogger(default="default value", skip=[ZeroDivisionError], verbose=True, loggerVarName="logger")
        def might_fail(self, x, y):
            self.logger.debug("Logger inside function definition")
            return x / y

    bar = Bar(my_logger)
    good_result = bar.might_fail(10, 2)  # Should succeed
    print("Good result: {}".format(good_result))
    bad_result = bar.might_fail(10, 0)  # Should log error and return default value
    print("Bad result: {}".format(bad_result))  # Should print "default value"

    print("\nTesting the MethodLogger class with specific logger ...")
    class Baz:
        def __init__(self):
            pass

        @MethodLogger(logger=my_logger, default="default value", skip=[ZeroDivisionError], verbose=True)
        def might_fail(self, x, y):
            return x / y

    baz = Baz()
    good_result = baz.might_fail(10, 2)  # Should succeed
    print("Good result: {}".format(good_result))
    bad_result = baz.might_fail(10, 0)  # Should log error and return default value
    print("Bad result: {}".format(bad_result))  # Should print "default value"

    print("\nAll tests passed successfully.")