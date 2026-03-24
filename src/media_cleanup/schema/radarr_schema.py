"""
TypedDict definitions mirroring Radarr API v3 response shapes.
See: https://radarr.video/docs/api/#/
"""

from typing import TypedDict, List, Optional


class Language(TypedDict):
    id: int
    name: str


class QualityDetails(TypedDict):
    id: int
    name: str
    source: str
    resolution: int


class QualityRevision(TypedDict):
    version: int
    real: int
    isRepack: bool


class QualityModel(TypedDict):
    quality: QualityDetails
    revision: QualityRevision


class MediaInfoResource(TypedDict):
    id: int
    audioBitrate: int
    audioChannels: float
    audioCodec: str
    audioLanguages: str
    audioStreamCount: int
    videoBitDepth: int
    videoBitrate: int
    videoCodec: str
    videoFps: float
    videoDynamicRange: str
    videoDynamicRangeType: str
    resolution: str
    runTime: str
    scanType: str
    subtitles: str


class MovieFileResource(TypedDict):
    """Represents a physical movie file on disk as returned by Radarr."""
    id: int
    movieId: int
    relativePath: Optional[str]
    path: Optional[str]
    size: int
    dateAdded: str  # ISO 8601
    sceneName: Optional[str]
    releaseGroup: Optional[str]
    languages: List[Language]
    quality: QualityModel
    mediaInfo: MediaInfoResource
    qualityCutoffNotMet: bool
    indexerFlags: Optional[int]


class Image(TypedDict):
    coverType: str
    url: str
    remoteUrl: str


class Ratings(TypedDict):
    votes: int
    value: float


class MovieStatistics(TypedDict):
    movieFileCount: int
    sizeOnDisk: int
    releaseGroups: List[str]


class Tag(TypedDict):
    """Radarr tag object from /api/v3/tag."""
    id: int
    label: str


class Movie(TypedDict):
    """Top-level movie object from /api/v3/movie."""
    id: int
    title: str
    originalTitle: str
    sortTitle: str
    sizeOnDisk: int
    status: str
    overview: str
    inCinemas: Optional[str]
    physicalRelease: Optional[str]
    digitalRelease: Optional[str]
    images: List[Image]
    year: int
    path: str
    qualityProfileId: int
    hasFile: bool
    movieFileId: int
    monitored: bool
    minimumAvailability: str
    isAvailable: bool
    folderName: str
    runtime: int
    cleanTitle: str
    imdbId: str
    tmdbId: int
    titleSlug: str
    rootFolderPath: str
    folder: str
    certification: Optional[str]
    genres: List[str]
    tags: List[int]  # list of tag IDs
    added: str
    ratings: Ratings
    movieFile: Optional[MovieFileResource]
    statistics: MovieStatistics
