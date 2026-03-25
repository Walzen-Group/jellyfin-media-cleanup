"""
Pydantic models mirroring Radarr API v3 response shapes.
See: https://radarr.video/docs/api/#/
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class Language(_Base):
    id: int
    name: str


class QualityDetails(_Base):
    id: int
    name: str
    source: str
    resolution: int


class QualityRevision(_Base):
    version: int
    real: int
    is_repack: bool


class QualityModel(_Base):
    quality: QualityDetails
    revision: QualityRevision


class MediaInfoResource(_Base):
    id: int = 0
    audio_bitrate: int = 0
    audio_channels: float = 0
    audio_codec: str = ""
    audio_languages: str = ""
    audio_stream_count: int = 0
    video_bit_depth: int = 0
    video_bitrate: int = 0
    video_codec: str = ""
    video_fps: float = 0
    video_dynamic_range: str = ""
    video_dynamic_range_type: str = ""
    resolution: str = ""
    run_time: str = ""
    scan_type: str = ""
    subtitles: str = ""


class MovieFileResource(_Base):
    """Represents a physical movie file on disk as returned by Radarr."""
    id: int
    movie_id: int = 0
    relative_path: str | None = None
    path: str | None = None
    size: int = 0
    date_added: str = ""
    scene_name: str | None = None
    release_group: str | None = None
    languages: list[Language] = []
    quality: QualityModel | None = None
    media_info: MediaInfoResource | None = None
    quality_cutoff_not_met: bool = False
    indexer_flags: int | None = None


class Image(_Base):
    cover_type: str
    url: str
    remote_url: str


class RatingEntry(_Base):
    votes: int = 0
    value: float = 0.0
    type: str = ""


class Ratings(_Base):
    """Radarr v3 ratings — nested per provider (imdb, tmdb, etc.) or flat legacy."""
    # Modern nested format
    imdb: RatingEntry | None = None
    tmdb: RatingEntry | None = None
    metacritic: RatingEntry | None = None
    rotten_tomatoes: RatingEntry | None = None
    # Legacy flat format fallback
    votes: int = 0
    value: float = 0.0


class MovieStatistics(_Base):
    movie_file_count: int
    size_on_disk: int
    release_groups: list[str]


class Tag(_Base):
    """Radarr tag object from /api/v3/tag."""
    id: int
    label: str


class Movie(_Base):
    """Top-level movie object from /api/v3/movie."""
    id: int
    title: str
    original_title: str = ""
    sort_title: str = ""
    size_on_disk: int = 0
    status: str = ""
    overview: str = ""
    in_cinemas: str | None = None
    physical_release: str | None = None
    digital_release: str | None = None
    images: list[Image] = []
    year: int = 0
    path: str
    quality_profile_id: int = 0
    has_file: bool = False
    movie_file_id: int = 0
    monitored: bool = False
    minimum_availability: str = ""
    is_available: bool = False
    folder_name: str = ""
    runtime: int = 0
    clean_title: str = ""
    imdb_id: str = ""
    tmdb_id: int = 0
    title_slug: str = ""
    root_folder_path: str = ""
    folder: str = ""
    certification: str | None = None
    genres: list[str] = []
    tags: list[int] = []
    added: str = ""
    ratings: Ratings | None = None
    movie_file: MovieFileResource | None = None
    statistics: MovieStatistics | None = None
