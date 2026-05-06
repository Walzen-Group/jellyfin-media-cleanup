"""
Unit tests for sonarr_schema types -- validates field coercions that have
caused production parse failures.
"""

from media_cleanup.schema.sonarr_schema import EpisodeFileResource


class TestEpisodeFileResourceMediaInfo:
    def test_float_audio_channels_and_video_fps_no_id(self) -> None:
        """Sonarr sometimes omits mediaInfo.id and sends fractional channel /
        FPS values (5.1, 23.976).  All three should parse without error."""
        data = {
            "id": 1,
            "seriesId": 10,
            "seasonNumber": 2,
            "relativePath": "Season 02/episode.mkv",
            "path": "/tv/show/Season 02/episode.mkv",
            "size": 1_500_000_000,
            "dateAdded": "2022-03-15T00:00:00Z",
            "languages": [],
            "quality": None,
            "customFormats": [],
            "customFormatScore": 0,
            "releaseType": "singleEpisode",
            "mediaInfo": {
                "audioChannels": 5.1,
                "videoFps": 23.976,
                "audioCodec": "AAC",
                "videoCodec": "x264",
                "resolution": "1920x1080",
                "runTime": "00:44:30",
                "scanType": "Progressive",
                "subtitles": "",
                "audioBitrate": 192000,
                "audioLanguages": "English",
                "audioStreamCount": 1,
                "videoBitDepth": 8,
                "videoBitrate": 4000000,
                "videoDynamicRange": "",
                "videoDynamicRangeType": "",
                # id intentionally omitted
            },
        }
        resource = EpisodeFileResource.model_validate(data, from_attributes=False)

        assert resource.media_info is not None
        assert resource.media_info.id is None
        assert resource.media_info.audio_channels == 5.1
        assert resource.media_info.video_fps == 23.976

    def test_integer_audio_channels_still_accepted(self) -> None:
        """Integer values (2, 6) must still parse into float fields."""
        data = {
            "id": 2,
            "seriesId": 11,
            "seasonNumber": 1,
            "languages": [],
            "quality": None,
            "customFormats": [],
            "customFormatScore": 0,
            "releaseType": "",
            "mediaInfo": {
                "audioChannels": 2,
                "videoFps": 24,
            },
        }
        resource = EpisodeFileResource.model_validate(data, from_attributes=False)

        assert resource.media_info is not None
        assert resource.media_info.audio_channels == 2.0
        assert resource.media_info.video_fps == 24.0

    def test_media_info_absent_is_none(self) -> None:
        """mediaInfo may be absent entirely (older Sonarr imports)."""
        data = {
            "id": 3,
            "seriesId": 12,
            "seasonNumber": 1,
            "languages": [],
            "quality": None,
            "customFormats": [],
            "customFormatScore": 0,
            "releaseType": "",
        }
        resource = EpisodeFileResource.model_validate(data, from_attributes=False)
        assert resource.media_info is None
