from stahovac.utils.system import open_folder_in_explorer


class TestOpenFolderInExplorer:
    def test_nonexistent_path(self):
        assert open_folder_in_explorer("/nonexistent/path/12345") is False

    def test_existent_path(self, tmp_path):
        assert open_folder_in_explorer(str(tmp_path)) is True
