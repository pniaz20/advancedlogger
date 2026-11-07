# Advanced Logger

[![Python tests](https://github.com/pniaz20/advancedlogger/actions/workflows/python-tests.yml/badge.svg?branch=main)](https://github.com/pniaz20/advancedlogger/actions/workflows/python-tests.yml)
[![PyPI version](https://img.shields.io/pypi/v/pniaz-advanced-logger?label=PyPI)](https://pypi.org/project/pniaz-advanced-logger/)
[![Python versions](https://img.shields.io/pypi/pyversions/pniaz-advanced-logger)](https://pypi.org/project/pniaz-advanced-logger/)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)](python/pyproject.toml)
[![License: MIT](https://img.shields.io/github/license/pniaz20/advancedlogger)](LICENSE)

Advanced, flexible logging for scripts, functions and class methods: colored, aligned log lines
that show which function emitted them, timestamped log files, and decorators that log calls and
errors without `try`/`except` boilerplate.

Each language has its own directory. Python is the only one so far.

| Directory | Language | Package |
| --- | --- | --- |
| [`python/`](python/) | Python 3.10+ (plus a Python 2.7 port) | [`pniaz-advanced-logger`](https://pypi.org/project/pniaz-advanced-logger/) on PyPI, imported as `advanced_logger` |

## Python

```bash
pip install pniaz-advanced-logger
```

```python
from advanced_logger import AdvancedLogger, MethodLogger, log_funcall, make_timestamped_logger
```

The PyPI name differs from the import name because `advanced-logger` on PyPI is an unrelated
project. Usage and the full API are in [`python/README.md`](python/README.md), which is also the
package's PyPI page.

Layout:

```text
python/
├── pyproject.toml           package metadata (version comes from advanced_logger.__version__)
├── README.md                user documentation, shown on PyPI
├── src/advanced_logger/
│   ├── adv_logging.py       Python 3.10+ implementation
│   ├── adv_logging_py2.py   Python 2.7 port of the same API
│   └── verbosity.py         Verbosity IntEnum
└── tests/                   pytest suite
```

### Developing

From the repository root, in the environment you work in:

```bash
pip install -e "./python[test]"   # editable: edits under python/src take effect immediately
pytest python/tests
```

### Releasing a new version

1. Bump `__version__` in `python/src/advanced_logger/__init__.py`. PyPI never accepts the same
   version twice, even after a deletion.
2. Build and check, from `python/`:

   ```bash
   python -m pip install --upgrade build twine
   rm -rf dist && python -m build
   python -m twine check --strict dist/*
   ```

3. Upload to TestPyPI first, then check that it installs:

   ```bash
   python -m twine upload --repository testpypi dist/*
   pip install --index-url https://test.pypi.org/simple/ pniaz-advanced-logger
   ```

4. Upload to PyPI:

   ```bash
   python -m twine upload dist/*
   ```

PyPI and TestPyPI do not accept account passwords for uploads. Create an API token under
*Account settings → API tokens* on each site (TestPyPI is a separate account), then give twine
the username `__token__` and the token, including its `pypi-` prefix, as the password. Twine
prompts for both if they are not in `~/.pypirc`.

## License

[MIT](LICENSE)
