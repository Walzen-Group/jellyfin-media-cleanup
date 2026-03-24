"""
Radarr API v3 client.

Fetches all movies from Radarr, resolves tags for "keep" filtering,
and exposes movie metadata + file paths for matching against Jellyfin watch history.
"""

import requests
from typing import Optional

from media_cleanup.schema.radarr_schema import Movie, Tag


class RadarrClient:
    def __init__(self, root_url: str, api_key: str) -> None:
        self.root_url = root_url
        self.api_key = api_key
        # Cache tags so we only fetch them once
        self._tags: Optional[list[Tag]] = None

    def get_all_movies(self) -> list[Movie]:
        """Fetch every movie from Radarr."""
        res = requests.get(
            f'{self.root_url}/api/v3/movie', headers=self._header)
        res.raise_for_status()
        return res.json()

    def get_tags(self) -> list[Tag]:
        """Fetch all tags from Radarr. Results are cached after first call."""
        if self._tags is None:
            res = requests.get(
                f'{self.root_url}/api/v3/tag', headers=self._header)
            res.raise_for_status()
            self._tags = res.json()
        return self._tags

    def get_keep_tag_id(self) -> Optional[int]:
        """
        Find the numeric ID of the "keep" tag.
        Returns None if no "keep" tag exists in Radarr.
        """
        tags = self.get_tags()
        for tag in tags:
            if tag['label'].lower() == 'keep':
                return tag['id']
        return None

    def filter_kept_movies(self, movies: list[Movie]) -> list[Movie]:
        """
        Remove movies that have the "keep" tag applied.
        If no "keep" tag exists in Radarr, returns all movies unchanged.
        """
        keep_tag_id = self.get_keep_tag_id()
        if keep_tag_id is None:
            return movies
        return [m for m in movies if keep_tag_id not in m['tags']]

    @property
    def _header(self) -> dict[str, str]:
        return {
            "X-Api-Key": self.api_key
        }
