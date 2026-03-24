"""
Sonarr API v3 client.

Fetches series metadata, resolves episode files by path, and supports
"keep" tag filtering to exclude protected series from cleanup.
"""

from dataclasses import dataclass
import requests
from pydantic import TypeAdapter
from rich.progress import Progress

from media_cleanup.schema.sonarr_schema import Series, EpisodeFileResource


# Reuse Tag from the Radarr schema — same shape
from media_cleanup.schema.radarr_schema import Tag

_series_list_adapter = TypeAdapter(list[Series])
_episode_file_list_adapter = TypeAdapter(list[EpisodeFileResource])
_tag_list_adapter = TypeAdapter(list[Tag])


@dataclass
class Result:
    metadata: Series
    original_path: str
    season: int = 0


class SonarrClient:
    def __init__(self, root_url: str, api_key: str) -> None:
        self.root_url = root_url
        self.api_key = api_key
        # Cache tags so we only fetch them once
        self._tags: list[Tag] | None = None

    # ------------------------------------------------------------------ #
    #  Series + episode file matching
    # ------------------------------------------------------------------ #

    def get_all_series(self) -> list[Series]:
        """Fetch every series from Sonarr."""
        res = requests.get(
            f'{self.root_url}/api/v3/series', headers=self._header)
        res.raise_for_status()
        return _series_list_adapter.validate_python(res.json())

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
        matching_series: list[Result] = [
            Result(metadata=series, original_path=file_path)
            for series in series_list
            for file_path in file_paths
            if series.path in file_path
        ]

        # Deduplicate by series ID (one entry per series)
        series_dict: dict[int, Result] = {
            result.metadata.id: result
            for result in matching_series
        }

        # Resolve season numbers by matching episode files
        task = None
        if progress:
            task = progress.add_task("Resolving episodes", total=len(series_dict))

        for series_id, result in series_dict.items():
            res = requests.get(
                f"{self.root_url}/api/v3/episodefile?seriesId={series_id}",
                headers=self._header)
            res.raise_for_status()
            episodes = _episode_file_list_adapter.validate_python(res.json())
            matched_episodes = [
                ep for ep in episodes
                if ep.path == result.original_path
            ]
            if matched_episodes:
                result.season = matched_episodes[0].season_number

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
            self._tags = _tag_list_adapter.validate_python(res.json())
        return self._tags

    def get_keep_tag_id(self) -> int | None:
        """
        Find the numeric ID of the "keep" tag.
        Returns None if no "keep" tag exists in Sonarr.
        """
        tags = self.get_tags()
        for tag in tags:
            if tag.label.lower() == 'keep':
                return tag.id
        return None

    def filter_kept_series(self, series_list: list[Series]) -> list[Series]:
        """
        Remove series that have the "keep" tag applied.
        If no "keep" tag exists in Sonarr, returns all series unchanged.
        """
        keep_tag_id = self.get_keep_tag_id()
        if keep_tag_id is None:
            return series_list
        return [s for s in series_list if keep_tag_id not in s.tags]

    # ------------------------------------------------------------------ #
    #  Auth
    # ------------------------------------------------------------------ #

    @property
    def _header(self) -> dict[str, str]:
        return {
            "X-Api-Key": self.api_key
        }
