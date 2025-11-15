from __future__ import print_function
import logging
import sys
import traceback
from functools import wraps
import warnings
import time
import os
import errno

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
MAX_FIELD_WIDTH = 20  # Adjust as needed


def ensure_dir(dirpath):
    try:
        os.makedirs(dirpath)
    except OSError as e:
        # It's OK if the directory exists
        if e.errno != errno.EEXIST or not os.path.isdir(dirpath):
            raise

def ensure_parent(filepath):
    ensure_dir(os.path.dirname(filepath))


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
        if record.levelno >= logging.ERROR:
            log_msg += "\n{}".format(traceback.format_exc()) if record.exc_info else ""
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
        if record.levelno >= logging.ERROR:
            log_msg += "\n{}".format(traceback.format_exc()) if record.exc_info else ""
        
        return log_msg


def get_logger(name, log_file=None, put_func_name=True, max_width=MAX_FIELD_WIDTH, custom_str="",
               time_format=None, colored_level=True, colored_log=False):
    """Get a custom logger with optional file logging."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Log everything

    # Console handler (colored log levels)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ConsoleFormatter(put_func_name=put_func_name,
                                                  max_width=max_width, custom_str=custom_str,
                                                  time_format=time_format, colored_level=colored_level,
                                                  colored_log=colored_log))

    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        logger.addHandler(console_handler)

    # File handler (plain text logs)
    if log_file:
        ensure_parent(log_file)
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setFormatter(FileFormatter(put_func_name=put_func_name,
                                                max_width=max_width, custom_str=custom_str,
                                                time_format=time_format))
        if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
            logger.addHandler(file_handler)

    # logger.warning("get_logger is deprecated; use AdvancedLogger class instead.")
    return logger


# Decorator for logging function calls
def log_funcall(logger=get_logger(__name__), default=None, skip=False, verbose=False):
    """Log function calls and handle exceptions. Not suitable for methods in classes.

    Args:
        logger (logging.Logger, optional): Logger object to use for logging. Defaults to `get_logger(__name__)`.
        default (Any, optional): Default value of the function. Defaults to None.
        skip (bool, optional): Whether to skip the function without throwing exceptions if any. Defaults to False.
        verbose (bool, optional): Whether to report start and finish of function run. Defaults to False.

    Raises:
        e: Error or Exception raised by the called function, if `skip` is False.

    Returns:
        A decorator that wraps the function to log its calls and handle exceptions.
    """
    # logger.warning("log_funcall is deprecated; use AdvancedLogger class instead.")
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                if verbose: logger.info("Calling {} ...".format(func.__name__))
                t1 = time.time()
                result = func(*args, **kwargs)
                t2 = time.time()
                if verbose: logger.info("Finished {} in {:.4f} seconds.".format(func.__name__, t2 - t1))
                return result
            except Exception as e:
                logger.error("Error in {}: {}".format(func.__name__, str(e)), exc_info=True)
                if skip:
                    logger.warning("Skipping {} due to error.".format(func.__name__))
                    return default
                else:
                    raise e # Re-raise exception
        return wrapper
    return decorator



def log_method_call(default=None, skip=False, verbose=False, loggerVarName="logger"):
    """Log class' method calls and handle exceptions.

    Args:
        default (Any, optional): Default value of the method. Defaults to None.
        skip (bool, optional): Whether to skip the method without throwing exceptions if any. Defaults to False.
        verbose (bool, optional): Whether to report start and finish of method run. Defaults to False.
        loggerVarName (str, optional): Name of the logger variable in the class. Defaults to "logger".

    Raises:
        e: Error or Exception raised by the called method, if `skip` is False.

    Returns:
        A decorator that wraps the method to log its calls and handle exceptions.
    """
    warnings.warn("log_method_call is deprecated; use MethodLogger instead.", DeprecationWarning)
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            self = args[0]  # The first argument is usually 'self'
            logger = getattr(self, loggerVarName, None)
            try:
                if verbose: logger.info("Calling {} ...".format(func.__name__))
                t1 = time.time()
                result = func(*args, **kwargs)
                t2 = time.time()
                if verbose: logger.info("Finished {} in {:.4f} seconds.".format(func.__name__, t2 - t1))
                return result
            except Exception as e:
                logger.error("Error in {}: {}".format(func.__name__, str(e)), exc_info=True)
                if skip:
                    logger.warning("Skipping {} due to error.".format(func.__name__))
                    return default
                else:
                    raise e # Re-raise exception
        return wrapper
    return decorator




class AdvancedLogger(logging.Logger):
    """
    A Logger subclass that:
    - automatically attaches a colored console handler (ConsoleFormatter)
    - optionally attaches a FileHandler (FileFormatter)
    - provides a decorator `@log_funcall(...)` to automatically catch-and-log exceptions
    """

    def __init__(self, name, log_file=None, put_func_name=True, max_width=MAX_FIELD_WIDTH, custom_str="",
                 time_format=None, colored_level=True, colored_log=False):
        """Initializes the AdvancedLogger class.
        This is a Logger subclass that:
        - automatically attaches a colored console handler (ConsoleFormatter)
        - optionally attaches a FileHandler (FileFormatter)
        - provides a decorator `@log_funcall(...)` to automatically catch-and-log exceptions

        ## Args:
        - name (str): Name attached to the logger instance. Defaults to `__name__`.
        - log_file (str, optional): File in which to write the logs. Defaults to None.
        - put_func_name (bool, optional): Whether to also put the name of the module/function making the log.
          Defaults to True.
        - max_width (int, optional): Maximum width for the module.function field. Defaults to MAX_FIELD_WIDTH.
        - custom_str (str, optional): Custom string to include in log messages. Defaults to "".
        - time_format (str, optional): Time format string for timestamps. Defaults to None (default format).
        - colored_level (bool, optional): Whether to color only the log level in console output. Defaults to True.
        - colored_log (bool, optional): Whether to color the entire log message in console output. Defaults to False.
        
        ## How to use this class

        ### 1. (Option A: explicit instantiation)
        
        You can simply create an instance of AdvancedLogger:
        ```
        from logger import AdvancedLogger
        logger = AdvancedLogger("myapp", log_file="logs/app.log")
        logger.info("This prints colored to console and also to logs/app.log")
        ```
        Then anywhere else you need it, you can import that `logger` object (or pass it around).

        ### 2. (Option B: make getLogger return AdvancedLogger automatically)
        
        If you want every time you call `logging.getLogger("someName")` to give you an
        `AdvancedLogger` instance instead of a plain `Logger`, you must call:
        ```
        import logging
        from path.to.this.module import AdvancedLogger
        logging.setLoggerClass(AdvancedLogger)
        # IMPORTANT: do this before any calls to logging.getLogger(...) in your code.
        ```
        Then:
        ```
        logger = logging.getLogger("myapp")
        # This `logger` is now an instance of AdvancedLogger, with console handler attached.
        logger.set_file("logs/app.log")   # if you want to add file output later
        logger.info("Hello, world")
        ```

        ### 3. Using the decorator:
        ```
        @logger.log_funcall(default="fallback", skip=True, verbose=True)
        def might_fail(x, y):
            return x / y

        result = might_fail(10, 0)
        # - Logs "Calling 'might_fail'"
        # - Catches ZeroDivisionError, logs it as ERR, logs a WRN about skipping
        # - Returns "fallback" instead of propagating the exception
        ```
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
        if log_file:
            ensure_parent(log_file)
            file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
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
            if isinstance(h, logging.StreamHandler):
                h.setFormatter(ConsoleFormatter(put_func_name=self.put_func_name,
                                                max_width=self.max_width, custom_str=self.custom_str,
                                                time_format=self.time_format, colored_level=self.colored_level,
                                                colored_log=self.colored_log))
            elif isinstance(h, logging.FileHandler):
                h.setFormatter(FileFormatter(put_func_name=self.put_func_name,
                                             max_width=self.max_width, custom_str=self.custom_str,
                                             time_format=self.time_format))
                
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
        ensure_parent(log_file)
        fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
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

    
    def log_funcall(self, default=None, skip=False, verbose=False):
        """
        Decorator factory. When you wrap a function with @logger.log_funcall(...),
        the wrapper will:
        - (if verbose) log "Calling <func_name>" at INFO level
        - execute the function
        - (if verbose) log "Finished <func_name>" at INFO level
        - if the function raises, log the error and either return `default` (if skip=True)
          or re-raise.
        
        ## Args:
        
        - default: The default return value of the wrapped function if an exception occurs.
        - skip: If True, the function will return `default` instead of raising the exception.
        - verbose: If True, logs additional information about function calls.
        
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if verbose:
                    self.info("Calling {!r} ...".format(func.__name__))
                try:
                    t1 = time.time()
                    result = func(*args, **kwargs)
                    t2 = time.time()
                    if verbose:
                        self.info("Finished {!r} in {:.4f} seconds.".format(func.__name__, t2 - t1))
                    return result
                except Exception as e:
                    # Log the exception with traceback
                    self.error("Error in {!r}: {}".format(func.__name__, str(e)), exc_info=True)
                    if skip:
                        self.warning("Skipping {!r} due to error.".format(func.__name__))
                        return default
                    else:
                        raise

            return wrapper

        return decorator





class MethodLogger(object):
    """
    A decorator factory class to log class method calls and handle exceptions.
    NOTE: Not suitable for standalone functions or static methods.
    """
    def __init__(self, logger=None, default=None, skip=False, verbose=False, loggerVarName="logger"):
        # Python 2 doesn't support keyword-only args. For Py2 usage,
        # pass these by name but they'll still be accepted.
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
                if self.verbose and logger:
                    logger.info("Calling %s", func.__name__)
                t1 = time.time()
                result = func(obj, *args, **kwargs)
                t2 = time.time()
                if self.verbose and logger:
                    logger.info("Finished %s in %.4f seconds", func.__name__, t2 - t1)
                return result

            except Exception as e:
                if logger:
                    logger.error("Error in %s: %s", func.__name__, e, exc_info=True)
                    if self.skip:
                        logger.warning("Skipping %s due to error.", func.__name__)
                        return self.default
                if self.skip:
                    return self.default
                raise
        return wrapped




def test_my_logger(logger):
    logger.debug("This is a debug message.")
    logger.info("This is an info message.")
    logger.warning("This is a warning message.")
    logger.error("This is an error message.")
    logger.critical("This is a critical message.")


if __name__ == "__main__":

    test_log_file1 = os.path.join(os.path.dirname(__file__), "test_logging", "AdvancedLogger_test1.log")
    test_log_file2 = os.path.join(os.path.dirname(__file__), "test_logging", "AdvancedLogger_test2.log")

    print("Instantiating AdvancedLogger and testing it ...")
    logger = AdvancedLogger("test_logger", log_file=test_log_file1, put_func_name=False)
    test_my_logger(logger)
    
    print("Testing set_func_name ...")
    logger.set_put_func_name(True)
    test_my_logger(logger)
    
    print("Testing set_max_width ...")
    logger.set_max_width(50)
    test_my_logger(logger)
    logger.reset_defaults()
    
    print("Testing set_time_format ...")
    logger.set_time_format("%Y-%m-%d %H:%M:%S")
    test_my_logger(logger)
    logger.reset_defaults()
    
    print("Testing set_coloring ...")
    print("All colored:")
    logger.set_coloring(colored_level=False, colored_log=True)
    test_my_logger(logger)
    print("No color:")
    logger.set_coloring(colored_level=False, colored_log=False)
    test_my_logger(logger)
    logger.reset_defaults()
    
    print("Testing set_custom_str ...")
    logger.set_custom_str("TEST1")
    test_my_logger(logger)
    logger.reset_defaults()
    
    print("Setting up logger for test_log_file2 ...")
    logger.set_file(test_log_file2)
    logger.set_coloring(colored_level=True, colored_log=False)
    logger.info("This message goes to AdvancedLogger_test2.log as well.")
    logger.debug("This is a debug message in AdvancedLogger_test2.log.")
    logger.warning("This is a warning message in AdvancedLogger_test2.log.")
    logger.error("This is an error message in AdvancedLogger_test2.log.")
    logger.critical("This is a critical message in AdvancedLogger_test2.log.")
    
    
    # print("Testing a function that may fail without the decorator ...")
    # def might_fail(x, y):
    #     return x / y
    # try:
    #     result = might_fail(10, 0)
    # except ZeroDivisionError as e:
    #     raise 
    
    logger.info("Testing the log_funcall decorator...")
    
    @logger.log_funcall(default="default value", skip=True, verbose=False)
    def might_fail(x, y):
        return x/y
    
    good_result = might_fail(10, 2)  # Should succeed
    print("Good result: {}".format(good_result))
    bad_result = might_fail(10, 0)  # Should log error and return default value
    print("Bad result: {}".format(bad_result))  # Should print "default value"
    
    logger.info("Testing the log_method_call decorator ...")
    class Foo:
        def __init__(self, logger):
            self.logger = logger
        
        @log_method_call(default="default value", skip=True, verbose=True, loggerVarName="logger")
        def might_fail(self, x, y):
            return x / y
    
    foo = Foo(logger)
    good_result = foo.might_fail(10, 2)  # Should succeed
    print("Good result: {}".format(good_result))
    bad_result = foo.might_fail(10, 0)  # Should log error and return default value
    print("Bad result: {}".format(bad_result))  # Should print "default value"
    
    logger.info("Testing the MethodLogger class without specific logger ...")
    class Bar:
        def __init__(self, logger):
            self.logger = logger
        
        @MethodLogger(default="default value", skip=True, verbose=True, loggerVarName="logger")
        def might_fail(self, x, y):
            return x / y
    
    bar = Bar(logger)
    good_result = bar.might_fail(10, 2)  # Should succeed
    print("Good result: {}".format(good_result))
    bad_result = bar.might_fail(10, 0)  # Should log error and return default value
    print("Bad result: {}".format(bad_result))  # Should print "default value"
    
    
    logger.info("Testing the MethodLogger class with specific logger ...")
    class Baz:
        def __init__(self):
            pass
        
        @MethodLogger(logger=logger, default="default value", skip=True, verbose=True)
        def might_fail(self, x, y):
            return x / y
    
    baz = Baz()
    good_result = baz.might_fail(10, 2)  # Should succeed
    print("Good result: {}".format(good_result))
    bad_result = baz.might_fail(10, 0)  # Should log error and return default value
    print("Bad result: {}".format(bad_result))  # Should print "default value"
    
    print("All tests passed successfully.")
    
    
    
    
    
    
    
    
    
    
    
    
        