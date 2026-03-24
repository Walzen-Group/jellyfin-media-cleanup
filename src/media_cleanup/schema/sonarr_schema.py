"""
Pydantic models mirroring Sonarr API v3 response shapes.
See: https://sonarr.tv/docs/api/
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class AlternateTitle(_Base):
    title: str = ""
    season_number: int = 0
    scene_season_number: int = 0
    scene_origin: str = ""
    comment: str = ""


class Image(_Base):
    cover_type: str = ""
    url: str = ""
    remote_url: str = ""


class OriginalLanguage(_Base):
    id: int
    name: str


class Statistics(_Base):
    next_airing: str | None = None
    previous_airing: str | None = None
    episode_file_count: int = 0
    episode_count: int = 0
    total_episode_count: int = 0
    size_on_disk: int = 0
    release_groups: list[str] = []
    percent_of_episodes: float = 0.0


class Season(_Base):
    season_number: int
    monitored: bool = False
    statistics: Statistics = Statistics()
    images: list[Image] = []


class AddOptions(_Base):
    ignore_episodes_with_files: bool = False
    ignore_episodes_without_files: bool = False
    monitor: str = ""
    search_for_missing_episodes: bool = False
    search_for_cutoff_unmet_episodes: bool = False


class Ratings(_Base):
    votes: int = 0
    value: float = 0.0


class Series(_Base):
    """Top-level series object from /api/v3/series."""
    id: int
    title: str
    alternate_titles: list[AlternateTitle] = []
    sort_title: str = ""
    status: str = ""
    ended: bool = False
    profile_name: str = ""
    overview: str = ""
    next_airing: str | None = None
    previous_airing: str | None = None
    network: str = ""
    air_time: str = ""
    images: list[Image] = []
    original_language: OriginalLanguage | None = None
    remote_poster: str = ""
    seasons: list[Season] = []
    year: int = 0
    path: str
    quality_profile_id: int = 0
    season_folder: bool = False
    monitored: bool = False
    monitor_new_items: str = ""
    use_scene_numbering: bool = False
    runtime: int = 0
    tvdb_id: int = 0
    tv_rage_id: int = 0
    tv_maze_id: int = 0
    tmdb_id: int = 0
    first_aired: str = ""
    last_aired: str = ""
    series_type: str = ""
    clean_title: str = ""
    imdb_id: str = ""
    title_slug: str = ""
    root_folder_path: str = ""
    folder: str = ""
    certification: str = ""
    genres: list[str] = []
    tags: list[int] = []
    added: str = ""
    add_options: AddOptions | None = None
    ratings: Ratings | None = None
    statistics: Statistics = Statistics()
    episodes_changed: bool = False


class EpisodeFile(_Base):
    series_id: int
    series_number: int
    relative_path: str


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


class SelectOption(_Base):
    value: int
    name: str
    order: int
    hint: str = ""


class Field(_Base):
    order: int
    name: str
    label: str
    unit: str = ""
    help_text: str = ""
    help_text_warning: str = ""
    help_link: str = ""
    value: str = ""
    type: str = ""
    advanced: bool = False
    select_options: list[SelectOption] = []
    select_options_provider_action: str = ""
    section: str = ""
    hidden: str = ""
    privacy: str = ""
    placeholder: str = ""
    is_float: bool = False


class Specification(_Base):
    id: int
    name: str
    implementation: str
    implementation_name: str
    info_link: str = ""
    negate: bool = False
    required: bool = False
    fields: list[Field] = []
    presets: list[str] = []


class CustomFormat(_Base):
    id: int
    name: str
    include_custom_format_when_renaming: bool = False
    specifications: list[Specification] = []


class MediaInfoResource(_Base):
    id: int
    audio_bitrate: int = 0
    audio_channels: int = 0
    audio_codec: str = ""
    audio_languages: str = ""
    audio_stream_count: int = 0
    video_bit_depth: int = 0
    video_bitrate: int = 0
    video_codec: str = ""
    video_fps: int = 0
    video_dynamic_range: str = ""
    video_dynamic_range_type: str = ""
    resolution: str = ""
    run_time: str = ""
    scan_type: str = ""
    subtitles: str = ""


class EpisodeFileResource(_Base):
    id: int
    series_id: int
    season_number: int
    relative_path: str | None = None
    path: str | None = None
    size: int = 0
    date_added: str = ""  # ISO 8601
    scene_name: str | None = None
    release_group: str | None = None
    languages: list[Language] = []
    quality: QualityModel | None = None
    custom_formats: list[CustomFormat] = []
    custom_format_score: int = 0
    indexer_flags: int | None = None
    release_type: str = ""
    media_info: MediaInfoResource | None = None
    quality_cutoff_not_met: bool = False
