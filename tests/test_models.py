from stahovac.models import VideoMetadata


class TestVideoMetadata:
    def test_from_dict_full(self):
        data = {
            "title": "Test Video",
            "uploader": "TestCreator",
            "duration": 3600,
            "thumbnail": "https://example.com/thumb.jpg",
            "description": "A test video description",
        }
        meta = VideoMetadata.from_dict(data)
        assert meta.title == "Test Video"
        assert meta.uploader == "TestCreator"
        assert meta.duration == 3600
        assert meta.thumbnail == "https://example.com/thumb.jpg"
        assert meta.description == "A test video description"

    def test_from_dict_empty(self):
        meta = VideoMetadata.from_dict({})
        assert meta.title == "Neznámý název"
        assert meta.uploader == "Neznámý autor"
        assert meta.duration == 0
        assert meta.thumbnail == ""
        assert meta.description == ""

    def test_from_dict_partial(self):
        data = {"title": "Only Title"}
        meta = VideoMetadata.from_dict(data)
        assert meta.title == "Only Title"
        assert meta.uploader == "Neznámý autor"
        assert meta.duration == 0
        assert meta.thumbnail == ""
        assert meta.description == ""
