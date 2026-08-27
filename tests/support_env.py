import importlib
import os
import tempfile


TEST_DB_PATH = os.path.join(tempfile.gettempdir(), f"neko_pos_test_suite_{os.getpid()}.db")

os.environ["APP_ENV"] = "test"
os.environ["TEST_SQLITE_PATH"] = TEST_DB_PATH


class TestDatabasePath:
    name = TEST_DB_PATH


TEST_DB = TestDatabasePath()


def import_web_app():
    return importlib.import_module("web_app")


def cleanup_test_db():
    if os.path.basename(TEST_DB_PATH).startswith("neko_pos_test_suite_"):
        try:
            os.unlink(TEST_DB_PATH)
        except OSError:
            pass
