import logging
from logging.handlers import RotatingFileHandler

from stahovac.utils.logging import configure_logging


def _file_handlers(path: str) -> list[logging.Handler]:
    return [h for h in logging.getLogger().handlers if getattr(h, "baseFilename", None) == path]


def _cleanup(path: str) -> None:
    for handler in _file_handlers(path):
        logging.getLogger().removeHandler(handler)
        handler.close()


class TestConfigureLogging:
    def test_writes_records_to_app_log(self, tmp_path):
        path = str(tmp_path / "app.log")
        _cleanup(path)
        try:
            configure_logging(tmp_path)
            logger = logging.getLogger("test.stahovac.logging")
            logger.warning("diagnostická zpráva 123")
            for handler in _file_handlers(path):
                handler.flush()
            content = (tmp_path / "app.log").read_text(encoding="utf-8")
            assert "diagnostická zpráva 123" in content
            assert "test.stahovac.logging" in content
        finally:
            _cleanup(path)

    def test_is_idempotent(self, tmp_path):
        path = str(tmp_path / "app.log")
        _cleanup(path)
        try:
            configure_logging(tmp_path)
            configure_logging(tmp_path)
            assert len(_file_handlers(path)) == 1
        finally:
            _cleanup(path)

    def test_creates_base_dir(self, tmp_path):
        nested = tmp_path / "nested" / "dir"
        path = str(nested / "app.log")
        _cleanup(path)
        try:
            configure_logging(nested)
            assert isinstance(_file_handlers(path)[0], RotatingFileHandler)
        finally:
            _cleanup(path)

    def test_never_raises_on_bad_dir(self, tmp_path):
        bad_file = tmp_path / "file"  # soubor, ne adresář -> mkdir selže
        bad_file.write_text("x")
        root_level = logging.getLogger().level
        try:
            configure_logging(bad_file / "sub")
        finally:
            for handler in list(logging.getLogger().handlers):
                if getattr(handler, "baseFilename", "").startswith(str(tmp_path)):
                    logging.getLogger().removeHandler(handler)
                    handler.close()
            logging.getLogger().setLevel(root_level)
