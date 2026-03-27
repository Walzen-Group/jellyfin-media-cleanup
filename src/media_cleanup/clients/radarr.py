"""
Radarr API v3 client.

Fetches all movies from Radarr, resolves tags for "keep" filtering,
and exposes movie metadata + file paths for matching against Jellyfin watch history.
"""

import requests
from pydantic import TypeAdapter

from media_cleanup.schema.radarr_schema import Movie, Tag

_movie_list_adapter = TypeAdapter(list[Movie])
_tag_list_adapter = TypeAdapter(list[Tag])


class RadarrClient:
    def __init__(self, root_url: str, api_key: str) -> None:
        self.root_url = root_url
        self.api_key = api_key
        # Cache tags so we only fetch them once
        self._tags: list[Tag] | None = None

    def get_all_movies(self) -> list[Movie]:
        """Fetch every movie from Radarr."""
        res = requests.get(
            f'{self.root_url}/api/v3/movie', headers=self._header)
        res.raise_for_status()
        return _movie_list_adapter.validate_python(res.json())

    def get_tags(self) -> list[Tag]:
        """Fetch all tags from Radarr. Results are cached after first call."""
        if self._tags is None:
            res = requests.get(
                f'{self.root_url}/api/v3/tag', headers=self._header)
            res.raise_for_status()
            self._tags = _tag_list_adapter.validate_python(res.json())
        return self._tags

    def get_keep_tag_id(self) -> int | None:
        """
        Find the numeric ID of the "keep" tag.
        Returns None if no "keep" tag exists in Radarr.
        """
        tags = self.get_tags()
        for tag in tags:
            if tag.label.lower() == 'keep':
                return tag.id
        return None

    def filter_kept_movies(self, movies: list[Movie]) -> list[Movie]:
        """
        Remove movies that have the "keep" tag applied.
        If no "keep" tag exists in Radarr, returns all movies unchanged.
        """
        keep_tag_id = self.get_keep_tag_id()
        if keep_tag_id is None:
            return movies
        return [m for m in movies if keep_tag_id not in m.tags]

    def delete_movie(self, movie_id: int, delete_files: bool = True) -> None:
        """Delete a movie from Radarr by its database ID.

        Args:
            movie_id: Radarr internal movie ID.
            delete_files: If True, also delete the movie file(s) from disk.
        """
        res = requests.delete(
            f'{self.root_url}/api/v3/movie/{movie_id}',
            params={"deleteFiles": str(delete_files).lower()},
            headers=self._header,
        )
        res.raise_for_status()

    @property
    def _header(self) -> dict[str, str]:
        return {
            "X-Api-Key": self.api_key
        }
