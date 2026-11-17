"""Finalize unreachable SQLite cursor/connection cycles before Windows cleanup."""
from contextlib import contextmanager
import gc


@contextmanager
def finalize_sqlite_fixture_cycles():
    """Run after assertions and before TemporaryDirectory removes fixture files.

    SQLite transaction contexts do not close connections. Cyclic garbage can
    therefore retain Windows file handles until the next GC collection. This
    does not suppress cleanup failures or close any live application resource.
    """
    try:
        yield
    finally:
        gc.collect()
