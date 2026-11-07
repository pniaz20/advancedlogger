import logging
import os
import uuid
from datetime import datetime, timedelta

import pytest

import advanced_logger
from advanced_logger import (
    AdvancedLogger,
    MethodLogger,
    Verbosity,
    clean_old_logs,
    log_funcall,
    make_timestamped_logger,
)


def _unique(name):
    # logging.Logger instances are global per name; keep tests independent.
    return "{}_{}".format(name, uuid.uuid4().hex[:8])


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def captured_logger(tmp_path):
    log = AdvancedLogger(_unique("test"), log_file=tmp_path / "test.log")
    handler = _ListHandler()
    log.addHandler(handler)
    log.captured = handler.records
    yield log
    for h in list(log.handlers):
        log.removeHandler(h)
        h.close()


def test_public_api_is_exported():
    for name in advanced_logger.__all__:
        assert hasattr(advanced_logger, name), name
    assert isinstance(advanced_logger.__version__, str)


def test_verbosity_ordering():
    assert Verbosity.NOTHING < Verbosity.MESSAGES < Verbosity.ALL_MESSAGES < Verbosity.EVERYTHING
    assert Verbosity.MESSAGES > 0


def test_advanced_logger_writes_file(tmp_path, captured_logger):
    captured_logger.info("hello %s", "file")
    for h in captured_logger.handlers:
        h.flush()
    text = (tmp_path / "test.log").read_text(encoding="utf-8")
    assert "hello file" in text
    assert "|INF]" in text
    assert "\033[" not in text  # no ANSI colors in the file


def test_custom_str_in_header(tmp_path, captured_logger):
    captured_logger.set_custom_str("RUN42")
    captured_logger.warning("tagged")
    for h in captured_logger.handlers:
        h.flush()
    assert "|RUN42|WRN] tagged" in (tmp_path / "test.log").read_text(encoding="utf-8")


def test_set_file_switches_log_file(tmp_path, captured_logger):
    new_file = tmp_path / "sub" / "other.log"
    captured_logger.set_file(new_file)
    captured_logger.error("moved")
    for h in captured_logger.handlers:
        h.flush()
    assert "moved" in new_file.read_text(encoding="utf-8")
    assert "moved" not in (tmp_path / "test.log").read_text(encoding="utf-8")
    assert captured_logger.log_file == os.fspath(new_file)


def test_log_funcall_injects_logger_as_global(captured_logger):
    @log_funcall(skip=[ZeroDivisionError], default="fallback")
    def divide(x, y):
        logger.info("dividing")  # noqa: F821  (injected by the decorator)
        return x / y

    assert divide(10, 2, logger=captured_logger) == 5
    assert divide(10, 0, logger=captured_logger) == "fallback"
    messages = [r.getMessage() for r in captured_logger.captured]
    assert "dividing" in messages
    assert any(m.startswith("Error in divide") for m in messages)
    # The injected global is removed again after each call.
    assert "logger" not in divide.__globals__


def test_log_funcall_forwards_explicit_logger_param(captured_logger):
    @log_funcall(logger=captured_logger)
    def uses_param(x, logger=None):
        return logger

    assert uses_param(1) is captured_logger


def test_log_funcall_reraises_unskipped(captured_logger):
    @log_funcall(logger=captured_logger, skip=[KeyError])
    def boom():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        boom()


def test_advanced_logger_log_funcall_method(captured_logger):
    @captured_logger.log_funcall(default=-1, skip=[ZeroDivisionError], verbose=True)
    def divide(x, y):
        return x / y

    assert divide(1, 0) == -1
    messages = [r.getMessage() for r in captured_logger.captured]
    assert any(m.startswith("Calling 'divide'") for m in messages)


def test_method_logger_uses_instance_logger(captured_logger):
    class Foo:
        def __init__(self, logger):
            self.logger = logger

        @MethodLogger(default="d", skip=[ZeroDivisionError], verbose=True)
        def div(self, x, y):
            return x / y

    foo = Foo(captured_logger)
    assert foo.div(4, 2) == 2
    assert foo.div(4, 0) == "d"
    levels = [r.levelname for r in captured_logger.captured]
    assert "ERROR" in levels and "WARNING" in levels


def test_method_logger_without_any_logger_still_skips():
    class Bar:
        @MethodLogger(default=0, skip=[ZeroDivisionError])
        def div(self, x, y):
            return x / y

    assert Bar().div(1, 0) == 0


def _decorator_records(records, name):
    """Records the decorators emitted about function *name* (not the ones its body logged)."""
    return [r for r in records if name in r.getMessage() and r.getMessage().split()[0] in
            ("Calling", "Finished", "Error", "Skipping")]


def _assert_attributed_to(records, name, code):
    """*code* is the decorated function's code object. Its first line is the decorator line, and
    every test function below raises two lines further down (decorator, def, return x / y)."""
    assert len(records) == 3, [r.getMessage() for r in records]  # Calling, Error, Skipping
    for r in records:
        assert r.funcName == name
        assert r.module == "test_adv_logging"
        assert r.pathname == code.co_filename
    calling, error, _skipping = records
    assert calling.lineno == code.co_firstlineno
    assert error.lineno == code.co_firstlineno + 2  # where the exception was raised inside it
    assert error.exc_info is not None and error.exc_info[0] is ZeroDivisionError


def test_log_funcall_attributes_records_to_decorated_function(captured_logger):
    @log_funcall(logger=captured_logger, skip=[ZeroDivisionError], verbose=True)
    def divide(x, y):
        return x / y

    divide(1, 0)
    _assert_attributed_to(_decorator_records(captured_logger.captured, "divide"), "divide",
                          divide.__wrapped__.__code__)


def test_logger_method_log_funcall_attributes_records_to_decorated_function(captured_logger):
    @captured_logger.log_funcall(skip=[ZeroDivisionError], verbose=True)
    def halve(x, y):
        return x / y

    halve(1, 0)
    _assert_attributed_to(_decorator_records(captured_logger.captured, "halve"), "halve",
                          halve.__wrapped__.__code__)


def test_method_logger_attributes_records_to_decorated_method(captured_logger):
    class Foo:
        def __init__(self, logger):
            self.logger = logger

        @MethodLogger(skip=[ZeroDivisionError], verbose=True)
        def ratio(self, x, y):
            return x / y

    Foo(captured_logger).ratio(1, 0)
    _assert_attributed_to(_decorator_records(captured_logger.captured, "ratio"), "ratio",
                          Foo.ratio.__wrapped__.__code__)


def test_log_method_call_attributes_records_to_decorated_method(captured_logger):
    with pytest.warns(DeprecationWarning):
        deco = advanced_logger.log_method_call(skip=[ZeroDivisionError], verbose=True)

    class Bar:
        def __init__(self, logger):
            self.logger = logger

        @deco
        def share(self, x, y):
            return x / y

    Bar(captured_logger).share(1, 0)
    _assert_attributed_to(_decorator_records(captured_logger.captured, "share"), "share",
                          Bar.share.__wrapped__.__code__)


def test_console_header_names_decorated_function(capsys):
    log = AdvancedLogger(_unique("hdr"), colored_level=False)
    try:
        @log_funcall(logger=log, verbose=True)
        def compute():
            return 1

        compute()
        out = capsys.readouterr().out
        assert "|test_adv_logging.compute" in out
        assert "wrapper" not in out
    finally:
        for h in list(log.handlers):
            log.removeHandler(h)
            h.close()


def test_level_filtering_still_applies(captured_logger):
    captured_logger.setLevel(logging.ERROR)

    @log_funcall(logger=captured_logger, verbose=True)
    def quiet():
        return 1

    quiet()
    assert _decorator_records(captured_logger.captured, "quiet") == []


@pytest.mark.skipif(not hasattr(__import__("inspect"), "getargspec"),
                    reason="the Python 2.7 port needs inspect.getargspec (Python <= 3.10)")
def test_py2_port_attributes_records_to_decorated_function():
    from advanced_logger import adv_logging_py2 as py2

    log = py2.AdvancedLogger(_unique("py2"))
    handler = _ListHandler()
    log.addHandler(handler)
    try:
        @py2.log_funcall(logger=log, skip=[ZeroDivisionError], verbose=True)
        def divide(x, y):
            return x / y

        class Foo(object):
            def __init__(self):
                self.logger = log

            @py2.MethodLogger(skip=[ZeroDivisionError], verbose=True)
            def ratio(self, x, y):
                return x / y

        divide(1, 0)
        Foo().ratio(1, 0)
        for name in ("divide", "ratio"):
            records = _decorator_records(handler.records, name)
            assert len(records) == 3
            assert all(r.funcName == name and r.module == "test_adv_logging" for r in records)
    finally:
        for h in list(log.handlers):
            log.removeHandler(h)
            h.close()


def test_make_timestamped_logger_layout(tmp_path):
    parent = tmp_path / "pipeline"
    log = make_timestamped_logger("pkg.pipeline.base.afford", parent_dir=parent)
    try:
        rel = os.path.relpath(log.log_file, parent).split(os.sep)
        assert rel[:3] == ["logs", "base", "afford"]
        assert rel[-1] == "afford.log"
        datetime.strptime(rel[3], "%Y%m%d_%H%M%S")
    finally:
        for h in list(log.handlers):
            log.removeHandler(h)
            h.close()


def test_clean_old_logs(tmp_path):
    fmt = "%Y%m%d_%H%M%S"
    old = (datetime.now() - timedelta(days=30)).strftime(fmt)
    new = datetime.now().strftime(fmt)
    for stamp in (old, new):
        d = tmp_path / "logs" / "mod" / stamp
        d.mkdir(parents=True)
        (d / "mod.log").write_text("x")

    preview = clean_old_logs(tmp_path, older_than="10 days ago", dry_run=True)
    assert [os.path.basename(p) for p in preview] == [old]
    assert (tmp_path / "logs" / "mod" / old).exists()

    deleted = clean_old_logs(tmp_path, older_than=10)
    assert [os.path.basename(p) for p in deleted] == [old]
    assert not (tmp_path / "logs" / "mod" / old).exists()
    assert (tmp_path / "logs" / "mod" / new).exists()


def test_clean_old_logs_rejects_bad_cutoff(tmp_path):
    (tmp_path / "logs").mkdir()
    with pytest.raises(ValueError):
        clean_old_logs(tmp_path, older_than="whenever")
    with pytest.raises(TypeError):
        clean_old_logs(tmp_path, older_than=True)
