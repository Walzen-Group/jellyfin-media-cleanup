"""
Sonarr API v3 client.

Fetches series metadata, resolves episode files by path, and supports
"keep" tag filtering to exclude protected series from cleanup.
"""

from typing import TypedDict, Optional
import requests
from rich.progress import Progress

from media_cleanup.schema.sonarr_schema import Series, EpisodeFileResource


class Tag(TypedDict):
    """Sonarr tag object from /api/v3/tag."""
    id: int
    label: str


class Result(TypedDict):
    metadata: Series
    original_path: str
    season: int


class SonarrClient:
    def __init__(self, root_url: str, api_key: str) -> None:
        self.root_url = root_url
        self.api_key = api_key
        # Cache tags so we only fetch them once
        self._tags: Optional[list[Tag]] = None

    # ------------------------------------------------------------------ #
    #  Series + episode file matching
    # ------------------------------------------------------------------ #

    def get_all_series(self) -> list[Series]:
        """Fetch every series from Sonarr."""
        res = requests.get(
            f'{self.root_url}/api/v3/series', headers=self._header)
        res.raise_for_status()
        return res.json()

    def match_paths_to_series(
        self, file_paths: list[str], progress: Progress | None = None
    ) -> dict[int, Result]:
        """
        Given a list of file paths (from Jellyfin), find which Sonarr series
        each path belongs to by checking if the series root path is a prefix.
        Then resolves the exact episode file to get the season number.

        Returns a dict keyed by series ID -> Result with metadata, path, and season.
        """
        series_list = self.get_all_series()

        # Match file paths to series by checking if series path is a prefix
        matching_series: list[dict] = [
            {
                "metadata": series,
                "original_path": file_path,
            }
            for series in series_list
            for file_path in file_paths
            if series["path"] in file_path
        ]

        # Deduplicate by series ID (one entry per series)
        series_dict: dict[int, dict] = {
            series["metadata"]["id"]: series
            for series in matching_series
        }

        # Resolve season numbers by matching episode files
        task = None
        if progress:
            task = progress.add_task("Resolving episodes", total=len(series_dict))

        for series_id, series in series_dict.items():
            res = requests.get(
                f"{self.root_url}/api/v3/episodefile?seriesId={series_id}",
                headers=self._header)
            res.raise_for_status()
            episodes: list[EpisodeFileResource] = res.json()
            matched_episodes = [
                ep for ep in episodes
                if ep["path"] == series["original_path"]
            ]
            if matched_episodes:
                matched_episode: EpisodeFileResource = matched_episodes[0]
                series_dict[series_id]["season"] = matched_episode["seasonNumber"]

            if progress and task is not None:
                progress.advance(task)

        return series_dict

    # ------------------------------------------------------------------ #
    #  Tag management + "keep" filtering
    # ------------------------------------------------------------------ #

    def get_tags(self) -> list[Tag]:
        """Fetch all tags from Sonarr. Results are cached after first call."""
        if self._tags is None:
            res = requests.get(
                f'{self.root_url}/api/v3/tag', headers=self._header)
            res.raise_for_status()
            self._tags = res.json()
        return self._tags

    def get_keep_tag_id(self) -> Optional[int]:
        """
        Find the numeric ID of the "keep" tag.
        Returns None if no "keep" tag exists in Sonarr.
        """
        tags = self.get_tags()
        for tag in tags:
            if tag['label'].lower() == 'keep':
                return tag['id']
        return None

    def filter_kept_series(self, series_list: list[Series]) -> list[Series]:
        """
        Remove series that have the "keep" tag applied.
        If no "keep" tag exists in Sonarr, returns all series unchanged.
        """
        keep_tag_id = self.get_keep_tag_id()
        if keep_tag_id is None:
            return series_list
        return [s for s in series_list if keep_tag_id not in s['tags']]

    # ------------------------------------------------------------------ #
    #  Auth
    # ------------------------------------------------------------------ #

    @property
    def _header(self) -> dict[str, str]:
        return {
            "X-Api-Key": self.api_key
        }
