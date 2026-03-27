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
    #  Deletion + season management
    # ------------------------------------------------------------------ #

    def get_series(self, series_id: int) -> dict:
        """GET /api/v3/series/{id}. Raises requests.HTTPError on 404."""
        res = requests.get(
            f'{self.root_url}/api/v3/series/{series_id}',
            headers=self._header,
        )
        res.raise_for_status()
        return res.json()

    def delete_series(self, series_id: int, delete_files: bool = True) -> None:
        """Delete a series from Sonarr by its database ID.

        Args:
            series_id: Sonarr internal series ID.
            delete_files: If True, also delete all files from disk.
        """
        res = requests.delete(
            f'{self.root_url}/api/v3/series/{series_id}',
            params={"deleteFiles": str(delete_files).lower()},
            headers=self._header,
        )
        res.raise_for_status()

    def get_episode_files(
        self, series_id: int, season_number: int | None = None
    ) -> list[EpisodeFileResource]:
        """Fetch episode files for a series, optionally filtered by season.

        Args:
            series_id: Sonarr internal series ID.
            season_number: If provided, only return files for this season.
        """
        res = requests.get(
            f'{self.root_url}/api/v3/episodefile',
            params={"seriesId": series_id},
            headers=self._header,
        )
        res.raise_for_status()
        files = _episode_file_list_adapter.validate_python(res.json())
        if season_number is not None:
            files = [f for f in files if f.season_number == season_number]
        return files

    def delete_episode_file(self, file_id: int) -> None:
        """Delete a single episode file by its ID."""
        res = requests.delete(
            f'{self.root_url}/api/v3/episodefile/{file_id}',
            headers=self._header,
        )
        res.raise_for_status()

    def delete_episode_files_bulk(self, file_ids: list[int]) -> None:
        """Delete multiple episode files in a single request.

        More efficient than calling delete_episode_file for each file.
        """
        res = requests.delete(
            f'{self.root_url}/api/v3/episodefile/bulk',
            json={"episodeFileIds": file_ids},
            headers=self._header,
        )
        res.raise_for_status()

    def unmonitor_season(self, series_id: int, season_number: int) -> None:
        """Set a season to unmonitored in Sonarr.

        Fetches the full series object, flips the monitored flag on the
        matching season, and PUTs the updated series back. Sonarr requires
        the full series object for updates.
        """
        # Fetch the current series
        res = requests.get(
            f'{self.root_url}/api/v3/series/{series_id}',
            headers=self._header,
        )
        res.raise_for_status()
        series_data: dict = res.json()

        # Find and update the matching season
        for season in series_data.get("seasons", []):
            if season.get("seasonNumber") == season_number:
                season["monitored"] = False
                break

        # PUT the modified series back
        res = requests.put(
            f'{self.root_url}/api/v3/series/{series_id}',
            json=series_data,
            headers=self._header,
        )
        res.raise_for_status()

    def tag_series(self, series_id: int, tag_id: int) -> None:
        """Add a tag to a series. Fetches current tags, appends, PUTs back."""
        series = self.get_series(series_id)
        tags = series.get("tags", [])
        if tag_id not in tags:
            tags.append(tag_id)
            series["tags"] = tags
            resp = requests.put(
                f"{self.root_url}/api/v3/series/{series_id}",
                json=series,
                headers=self._header,
            )
            resp.raise_for_status()

    # ------------------------------------------------------------------ #
    #  Auth
    # ------------------------------------------------------------------ #

    @property
    def _header(self) -> dict[str, str]:
        return {
            "X-Api-Key": self.api_key
        }
