from pathlib import Path

from stahovac.utils.paths import get_base_dir, set_base_dir


class TestPaths:
    def test_set_and_get_base_dir(self):
        custom_path = Path("/tmp/test_aether")
        set_base_dir(custom_path)
        assert get_base_dir() == custom_path

    def test_get_base_dir_default(self):
        set_base_dir(None)
        path = get_base_dir()
        assert isinstance(path, Path)
        assert path.exists()
