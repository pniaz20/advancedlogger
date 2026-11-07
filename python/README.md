# advanced_logger

[![Python tests](https://github.com/pniaz20/advancedlogger/actions/workflows/python-tests.yml/badge.svg?branch=main)](https://github.com/pniaz20/advancedlogger/actions/workflows/python-tests.yml)
[![PyPI version](https://img.shields.io/pypi/v/pniaz-advanced-logger?label=PyPI)](https://pypi.org/project/pniaz-advanced-logger/)
[![Python versions](https://img.shields.io/pypi/pyversions/pniaz-advanced-logger)](https://pypi.org/project/pniaz-advanced-logger/)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)](https://github.com/pniaz20/advancedlogger/blob/main/python/pyproject.toml)
[![License: MIT](https://img.shields.io/github/license/pniaz20/advancedlogger)](https://github.com/pniaz20/advancedlogger/blob/main/LICENSE)

Advanced, flexible logging for Python scripts, functions and class methods.

```bash
pip install pniaz-advanced-logger
```

```python
import advanced_logger
```

The PyPI distribution is called `pniaz-advanced-logger`; the package you import is
`advanced_logger`. (The PyPI name `advanced-logger` belongs to an unrelated project.)

Requires Python 3.10 or newer and has no dependencies. A Python 2.7 port of the same API is
included; see [Python 2.7](#python-27).

## What it gives you

- **`AdvancedLogger`**, a regular `logging.Logger` subclass, so it works anywhere a logger does.
  Every line carries a timestamp, the `module.function` that emitted it (padded to a fixed
  width so lines align), an optional custom tag, and a three-letter level (`DBG`, `INF`, `WRN`,
  `ERR`, `CRT`). On the console the level is colored; the log file gets the same lines without
  color codes.
- **Decorators that log for you.** `@log_funcall` (functions) and `@MethodLogger` (methods)
  log the call, its duration and any exception with its traceback. For the exception types you
  list in `skip`, they return a `default` value instead of raising, so you don't need
  `try`/`except` blocks full of logging calls.
- **Timestamped log files.** `make_timestamped_logger` gives each run its own log file in
  `<parent_dir>/logs/<module path>/<timestamp>/<module>.log`, and `clean_old_logs` deletes
  runs older than a cutoff.

## Quick start

```python
from advanced_logger import AdvancedLogger, MethodLogger, log_funcall

log = AdvancedLogger("demo", log_file="logs/demo.log")


@log_funcall(skip=[ZeroDivisionError], default=float("nan"), verbose=True)
def ratio(a, b):
    logger.info("computing %s / %s", a, b)   # `logger` is provided by the decorator
    return a / b


class Robot:
    def __init__(self):
        self.logger = log                       # MethodLogger looks for `self.logger`

    @MethodLogger(skip=[RuntimeError], default=False)
    def grasp(self):
        raise RuntimeError("gripper not responding")


ratio(1, 0, logger=log)   # logs the error and traceback, then returns nan
Robot().grasp()           # logs the error and traceback, then returns False
```

Console output (tracebacks shortened):

```text
[2026-11-07 22:38:41,507|demo.ratio                             |INF] Calling ratio ...
[2026-11-07 22:38:41,507|demo.ratio                             |INF] computing 1 / 0
[2026-11-07 22:38:41,507|demo.ratio                             |ERR] Error in ratio: division by zero
Traceback (most recent call last):
  ...
ZeroDivisionError: division by zero
[2026-11-07 22:38:41,507|demo.ratio                             |WRN] Skipping ratio (ZeroDivisionError) due to error.
[2026-11-07 22:38:41,507|demo.grasp                             |ERR] Error in grasp: gripper not responding
Traceback (most recent call last):
  ...
RuntimeError: gripper not responding
[2026-11-07 22:38:41,508|demo.grasp                             |WRN] Skipping grasp (RuntimeError) due to error.
```

Lines written by the decorators carry the decorated function's own module, name, source file
and line number, as if the function had logged them itself. For errors, the line number is
where the exception was raised inside that function. Handlers and formatters that show
`%(lineno)d` or `%(pathname)s` therefore point into your code, not into this package.

## `AdvancedLogger`

```python
AdvancedLogger(
    name,                 # logger name, typically __name__
    log_file=None,        # also write to this file (parent directories are created)
    put_func_name=True,   # show module.function in each line
    max_width=40,         # width of the module.function field
    custom_str="",        # extra tag shown in every line, e.g. a run ID
    time_format=None,     # strftime format for the timestamp; None uses logging's default
    colored_level=True,   # color the level on the console
    colored_log=False,    # color the whole console line (except INF lines)
)
```

The logger level is `DEBUG`, so everything is shown. Each option can be changed later:
`set_file(path)`, `set_custom_str(s)`, `set_put_func_name(b)`, `set_max_width(n)`,
`set_time_format(fmt)`, `set_coloring(colored_level, colored_log)`. `reset_defaults()` restores
the formatting defaults and keeps the current log file.

`get_logger(name, log_file=None, ...)` takes the same options and configures a logger from
`logging.getLogger(name)` instead of creating an `AdvancedLogger`. It adds no handler the logger
already has, so you can call it repeatedly with the same name.

## Decorating functions: `log_funcall`

```python
log_funcall(logger=None, default=None, skip=None, verbose=False, logger_var_name="logger")
```

- `skip`: list of exception types. A matching exception is logged and `default` is returned.
  Any other exception is logged and then re-raised. With `skip=None` every exception is
  re-raised after logging.
- `verbose=True`: also log `Calling <name> ...` and `Finished <name> in <t> seconds.`.
- **Which logger is used**, highest priority first: a `logger=` keyword argument passed at call
  time, the `logger` given to the decorator, then a fallback console logger.
- **How the function body gets it.** If the function has a `logger` parameter, the resolved
  logger is passed in as that argument. Otherwise, the logger is put into the function's module
  globals under the name `logger` for the duration of the call and removed afterwards, so the
  body can use `logger` without declaring it. If the function takes `**kwargs`, `logger` is left
  in `kwargs` and nothing is injected. `logger_var_name` changes the name used for all of this.

Putting the logger into module globals is not thread-safe. If the function may run in several
threads at once, give it an explicit `logger` parameter.

`AdvancedLogger` has the same decorator as a method, which uses that logger as the fallback:

```python
log = AdvancedLogger("demo")

@log.log_funcall(skip=[KeyError], default={})
def load(name):
    ...
```

## Decorating methods: `MethodLogger`

```python
MethodLogger(logger=None, default=None, skip=None, verbose=False, loggerVarName="logger")
```

Uses `logger` if given; otherwise the instance attribute named by `loggerVarName` (default
`self.logger`). If neither exists, nothing is logged, but `skip` and `default` still apply.
`log_method_call` is an older, deprecated function form of the same decorator.

## Timestamped log files

```python
from advanced_logger import make_timestamped_logger, clean_old_logs

logger = make_timestamped_logger(name=__name__, parent_dir="/path/to/project")
```

For a module named `mypkg.vision.detector`, this writes to
`/path/to/project/logs/vision/detector/20261107_222431/detector.log`. The top-level package
name is dropped from the path. If the last component of `parent_dir` appears in the module
name, only the part after it is used: with `parent_dir=".../mypkg/vision"`, the same module logs
to `.../mypkg/vision/logs/detector/<timestamp>/detector.log`. Extra keyword arguments are passed
to `AdvancedLogger`. `format=` changes the timestamp format (default `"%Y%m%d_%H%M%S"`).

```python
clean_old_logs("/path/to/project")                                  # older than 10 days
clean_old_logs("/path/to/project", older_than="2 weeks ago", dry_run=True)   # preview only
clean_old_logs("/path/to/project", older_than=datetime(2026, 1, 1))
```

`clean_old_logs` deletes whole `<timestamp>` directories under `<parent_dir>/logs` that are older
than `older_than`, then removes directories left empty. `older_than` can be a `datetime`, a
`date`, a number of days, a timestamp string in `fmt`, or a phrase such as `"10 days ago"`,
`"3 weeks"` or `"48h"`. It returns the paths it deleted (or, with `dry_run=True`, would delete).
If `fmt` differs from the `format` you passed to `make_timestamped_logger`, pass the same value.

## `Verbosity`

An `IntEnum` with `NOTHING = 0`, `MESSAGES = 1`, `ALL_MESSAGES = 2` and `EVERYTHING = 3`, for
functions that take a `verbose` argument:

```python
from advanced_logger import Verbosity

def plan(goal, verbose=Verbosity.MESSAGES):
    if verbose > Verbosity.MESSAGES:
        logger.debug("details ...")
```

## Python 2.7

`advanced_logger/adv_logging_py2.py` is a port of the same API to Python 2.7, without type hints
and signature rewriting. The package on PyPI requires Python 3.10, so on Python 2.7 use the
source: either put `python/src` from the
[repository](https://github.com/pniaz20/advancedlogger) on `PYTHONPATH` and import
`advanced_logger.adv_logging_py2`, or copy that single file into your project. It uses only the
standard library.

```python
from advanced_logger.adv_logging_py2 import AdvancedLogger, MethodLogger, log_funcall
```

## License

MIT. Source and issues: <https://github.com/pniaz20/advancedlogger>
