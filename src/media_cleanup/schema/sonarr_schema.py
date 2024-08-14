from typing import TypedDict, List, Optional

class AlternateTitle(TypedDict):
    title: str
    seasonNumber: int
    sceneSeasonNumber: int
    sceneOrigin: str
    comment: str

class Image(TypedDict):
    coverType: str
    url: str
    remoteUrl: str

class OriginalLanguage(TypedDict):
    id: int
    name: str

class Statistics(TypedDict):
    nextAiring: Optional[str]
    previousAiring: Optional[str]
    episodeFileCount: int
    episodeCount: int
    totalEpisodeCount: int
    sizeOnDisk: int
    releaseGroups: List[str]
    percentOfEpisodes: int

class Season(TypedDict):
    seasonNumber: int
    monitored: bool
    statistics: Statistics
    images: List[Image]

class AddOptions(TypedDict):
    ignoreEpisodesWithFiles: bool
    ignoreEpisodesWithoutFiles: bool
    monitor: str
    searchForMissingEpisodes: bool
    searchForCutoffUnmetEpisodes: bool

class Ratings(TypedDict):
    votes: int
    value: int

class Series(TypedDict):
    id: int
    title: str
    alternateTitles: List[AlternateTitle]
    sortTitle: str
    status: str
    ended: bool
    profileName: str
    overview: str
    nextAiring: Optional[str]
    previousAiring: Optional[str]
    network: str
    airTime: str
    images: List[Image]
    originalLanguage: OriginalLanguage
    remotePoster: str
    seasons: List[Season]
    year: int
    path: str
    qualityProfileId: int
    seasonFolder: bool
    monitored: bool
    monitorNewItems: str
    useSceneNumbering: bool
    runtime: int
    tvdbId: int
    tvRageId: int
    tvMazeId: int
    tmdbId: int
    firstAired: str
    lastAired: str
    seriesType: str
    cleanTitle: str
    imdbId: str
    titleSlug: str
    rootFolderPath: str
    folder: str
    certification: str
    genres: List[str]
    tags: List[int]
    added: str
    addOptions: AddOptions
    ratings: Ratings
    statistics: Statistics
    episodesChanged: bool

class EpisodeFile(TypedDict):
    seriesId: int
    seriesNumber: int
    relativePath: str


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

class SelectOption(TypedDict):
    value: int
    name: str
    order: int
    hint: str

class Field(TypedDict):
    order: int
    name: str
    label: str
    unit: str
    helpText: str
    helpTextWarning: str
    helpLink: str
    value: str
    type: str
    advanced: bool
    selectOptions: List[SelectOption]
    selectOptionsProviderAction: str
    section: str
    hidden: str
    privacy: str
    placeholder: str
    isFloat: bool

class Specification(TypedDict):
    id: int
    name: str
    implementation: str
    implementationName: str
    infoLink: str
    negate: bool
    required: bool
    fields: List[Field]
    presets: List[str]

class CustomFormat(TypedDict):
    id: int
    name: str
    includeCustomFormatWhenRenaming: bool
    specifications: List[Specification]

class MediaInfoResource(TypedDict):
    id: int
    audioBitrate: int
    audioChannels: int
    audioCodec: str
    audioLanguages: str
    audioStreamCount: int
    videoBitDepth: int
    videoBitrate: int
    videoCodec: str
    videoFps: int
    videoDynamicRange: str
    videoDynamicRangeType: str
    resolution: str
    runTime: str
    scanType: str
    subtitles: str

class EpisodeFileResource(TypedDict):
    id: int
    seriesId: int
    seasonNumber: int
    relativePath: Optional[str]
    path: Optional[str]
    size: int
    dateAdded: str  # ISO 8601 date-time format
    sceneName: Optional[str]
    releaseGroup: Optional[str]
    languages: List[Language]
    quality: QualityModel
    customFormats: List[CustomFormat]
    customFormatScore: int
    indexerFlags: Optional[int]
    releaseType: str  # Enum-like string
    mediaInfo: MediaInfoResource
    qualityCutoffNotMet: bool
