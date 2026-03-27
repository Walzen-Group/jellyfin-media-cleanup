"""
Jellyfin API client.

Queries the Playback Reporting plugin's custom SQL endpoint to find
movies and series based on watch history thresholds. Resolves item IDs
to file paths via the Jellyfin /items endpoint, chunked to avoid URI
length limits.

For series, a single query fetches ALL ever-watched episodes with their
most recent play date. Episode ItemNames are parsed locally, then one
representative episode per unique show is resolved via the /items API
to obtain a file path for Sonarr path matching.
"""

import requests as re
from typing import Callable, TypedDict

from media_cleanup.types import EpisodeInfo

# Generic progress callback: (step_name, current, total)
ProgressCallback = Callable[[str, int, int], None]

# Optional cancel check: return True to abort between chunks
CancelCheck = Callable[[], bool]


# ------------------------------------------------------------------ #
#  API response schemas
# ------------------------------------------------------------------ #

MediaSourceSchema = TypedDict('MediaSourceSchema',
                              {
                                  'Path': str
                              })

ItemResponseSchema = TypedDict('ItemResponseSchema',
                               {
                                   'Id': str,
                                   'Name': str,
                                   'MediaSources': list[MediaSourceSchema]
                               })

PlaybackResponseSchema = TypedDict('PlaybackResponseSchema',
                                   {
                                       "colums": list[str],  # yes there is a typo in the plugin api
                                       "results": list[list]
                                   })


class JellyfinClient:

    """
    this is ballpark estimation for how many ids can be requested at once,
    since they are a query parameter and uri gets too large
    """
    chunk_length = 200

    def __init__(self, root_url: str, api_key: str) -> None:
        self.root_url = root_url
        self.api_key = api_key

    # ------------------------------------------------------------------ #
    #  Playback Reporting queries
    # ------------------------------------------------------------------ #

    def _query_playback(self, sql: str) -> PlaybackResponseSchema:
        """
        Execute a custom SQL query against the Playback Reporting plugin.
        Returns the raw response with 'colums' (sic) and 'results' keys.
        """
        res = re.post(
            f'{self.root_url}/user_usage_stats/submit_custom_query',
            headers=self._header,
            json={
                "CustomQueryString": sql,
                "ReplaceUserId": True
            })
        res.raise_for_status()
        return res.json()

    def _extract_item_ids(self, response: PlaybackResponseSchema) -> list[str]:
        """Pull the ItemId column out of a Playback Reporting response."""
        item_id_column_number = response['colums'].index('ItemId')
        return [r[item_id_column_number] for r in response["results"]]

    # ------------------------------------------------------------------ #
    #  Movies
    # ------------------------------------------------------------------ #

    def get_recently_watched_movies(self, month_count: int) -> list[str]:
        """
        Get item IDs for movies watched within the last `month_count` months.
        Only includes plays longer than 200 seconds (filters out accidental clicks).
        """
        sql = (
            "SELECT * \n"
            "FROM PlaybackActivity \n"
            f"WHERE PlayDuration > 200 "
            f"AND DateCreated >= date('now','-{month_count} month') "
            "AND ItemType LIKE 'Movie' \n"
            "GROUP BY ItemId \n"
            "ORDER BY DateCreated DESC"
        )
        response = self._query_playback(sql)
        return self._extract_item_ids(response)

    def get_not_recently_watched_movies(self, month_count: int) -> list[str]:
        """
        Get item IDs for movies whose most recent watch was MORE than
        `month_count` months ago. Uses MAX(DateCreated) so a movie only
        appears if ALL its plays are older than the threshold.
        """
        sql = (
            "SELECT *, MAX(DateCreated) as LastPlayed \n"
            "FROM PlaybackActivity \n"
            "WHERE PlayDuration > 200 "
            "AND ItemType LIKE 'Movie' \n"
            "GROUP BY ItemId \n"
            f"HAVING LastPlayed < date('now','-{month_count} month') \n"
            "ORDER BY LastPlayed DESC"
        )
        response = self._query_playback(sql)
        return self._extract_item_ids(response)

    # ------------------------------------------------------------------ #
    #  Series / Episodes
    # ------------------------------------------------------------------ #

    def get_all_watched_episode_dates(self) -> dict[str, dict[str, str]]:
        """
        Get every ever-watched episode with its most recent play date and name.

        Returns a dict mapping Jellyfin item ID -> {"last_played": ..., "item_name": ...}.
        ItemName is kept as a fallback for episodes whose IDs can no longer be
        resolved via the /items API (e.g. after a library re-scan changes IDs).

        Only includes plays longer than 200 seconds.
        """
        sql = (
            "SELECT ItemId, ItemName, MAX(DateCreated) as LastPlayed \n"
            "FROM PlaybackActivity \n"
            "WHERE PlayDuration > 200 AND ItemType LIKE 'Episode' \n"
            "GROUP BY ItemId \n"
            "ORDER BY LastPlayed DESC"
        )
        response = self._query_playback(sql)
        item_id_col = response['colums'].index('ItemId')
        item_name_col = response['colums'].index('ItemName')
        last_played_col = response['colums'].index('LastPlayed')
        return {
            r[item_id_col]: {
                "last_played": r[last_played_col],
                "item_name": r[item_name_col],
            }
            for r in response['results']
        }

    def parse_episode_dates(
        self,
        item_dates: dict[str, dict[str, str]],
    ) -> list[EpisodeInfo]:
        """
        Parse episode ItemNames from PlaybackActivity into EpisodeInfo records.

        Pure string parsing, no HTTP calls. Episodes whose ItemName can't be
        parsed are skipped (counted as "skipped" in EpisodeStats).
        """
        results: list[EpisodeInfo] = []
        for item_id, info in item_dates.items():
            item_name = info.get('item_name', '')
            if not item_name:
                continue
            series_name, season_number = self._parse_episode_item_name(item_name)
            if not series_name:
                continue
            results.append(EpisodeInfo(
                item_id=item_id,
                series_name=series_name,
                season_number=season_number,
                last_played=info['last_played'],
            ))
        return results

    def resolve_series_paths(
        self,
        episodes: list[EpisodeInfo],
        precise: bool = False,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> dict[str, list[str]]:
        """
        Resolve episode IDs via the /items API to obtain file paths for
        Sonarr path matching.

        Returns a dict mapping normalized series_name -> list of file paths.

        When precise=False (default), resolves one representative episode per
        unique show. Fast, but if the same series exists in multiple Jellyfin
        libraries (e.g. /tv/Show and /tv-ger/Show), only one path is returned.

        When precise=True, resolves ALL episodes and collects all unique paths
        per show. Slower, but correctly handles multi-library setups.
        """
        from collections import defaultdict
        from media_cleanup.matching import normalize_title

        if precise:
            # Resolve all episode IDs
            ids_to_resolve = [ep.item_id for ep in episodes]
        else:
            # Pick one episode ID per unique show (normalized name)
            show_representatives: dict[str, str] = {}  # norm_name -> item_id
            for ep in episodes:
                norm = normalize_title(ep.series_name)
                if norm not in show_representatives:
                    show_representatives[norm] = ep.item_id
            ids_to_resolve = list(show_representatives.values())

        if not ids_to_resolve:
            return {}

        cb = progress_callback or (lambda *_: None)
        results: dict[str, set[str]] = defaultdict(set)
        total = len(ids_to_resolve)
        resolved_count = 0
        chunks = list(range(0, total, self.chunk_length))

        for i in chunks:
            if cancel_check and cancel_check():
                from media_cleanup.service import CancellationError
                raise CancellationError("Pipeline cancelled by caller")
            chunk = ids_to_resolve[i:i + self.chunk_length]
            res = re.get(
                f'{self.root_url}/items'
                f'?ids={",".join(chunk)}'
                f'&fields=MediaSources',
                headers=self._header)
            res.raise_for_status()

            returned_count = 0
            for item in res.json().get('Items', []):
                returned_count += 1
                series_name = item.get('SeriesName', '')
                media_sources = item.get('MediaSources', [])
                if not series_name or not media_sources:
                    resolved_count += 1
                    cb("Resolving show paths", resolved_count, total)
                    continue
                file_path = media_sources[0].get('Path', '')
                if file_path:
                    norm = normalize_title(series_name)
                    results[norm].add(file_path)
                resolved_count += 1
                cb(f"Resolving show paths: {series_name}", resolved_count, total)

            # Advance past stale IDs the API didn't return
            stale_count = len(chunk) - returned_count
            if stale_count > 0:
                resolved_count += stale_count
                cb("Resolving show paths", resolved_count, total)

        return {k: list(v) for k, v in results.items()}

    @staticmethod
    def _parse_episode_item_name(item_name: str) -> tuple[str, int]:
        """
        Parse a Jellyfin PlaybackActivity ItemName for episodes.

        Format: "Series Name - s01e05 - Episode Title"
        Returns (series_name, season_number). If the pattern doesn't match,
        returns (full item_name as series_name, -1 for unknown season).
        """
        import re as regex
        # Match "Series Name - s01e05" pattern (case-insensitive)
        match = regex.match(r'^(.+?)\s+-\s+[Ss](\d+)[Ee]\d+', item_name)
        if match:
            return match.group(1).strip(), int(match.group(2))
        return item_name.strip(), -1

    # ------------------------------------------------------------------ #
    #  File path resolution (movies)
    # ------------------------------------------------------------------ #

    def get_file_paths(
        self,
        ids: list[str],
        progress_callback: ProgressCallback | None = None,
        desc: str = "Resolving file paths",
        cancel_check: CancelCheck | None = None,
    ) -> list[str]:
        """
        Resolve a list of Jellyfin item IDs to their on-disk file paths.
        Automatically chunks requests to stay under URI length limits.

        Args:
            ids: Jellyfin item IDs to resolve.
            progress_callback: Optional (step, current, total) callback.
            desc: Label shown in the progress step name.
        """
        results: list[str] = []
        chunks = list(range(0, len(ids), self.chunk_length))
        cb = progress_callback or (lambda *_: None)

        for idx, i in enumerate(chunks):
            if cancel_check and cancel_check():
                from media_cleanup.service import CancellationError
                raise CancellationError("Pipeline cancelled by caller")
            results.extend(
                self._get_file_paths_for_chunk_length(ids[i:i + self.chunk_length]))
            cb(desc, idx + 1, len(chunks))

        return results

    def _get_file_paths_for_chunk_length(self, ids: list[str]) -> list[str]:
        """Fetch file paths for a single chunk of item IDs."""
        if len(ids) > self.chunk_length:
            raise ValueError('request URI will be too large with this many ids')
        res = re.get(
            f'{self.root_url}/items?ids={",".join(ids)}&fields=MediaSources',
            headers=self._header)
        res.raise_for_status()
        return [self._get_item_path(item) for item in res.json()['Items']]

    def _get_item_path(self, item: ItemResponseSchema) -> str:
        """Extract the single file path from a Jellyfin item response."""
        media_details = f"{item['Id']} {item['MediaSources']}"
        media_sources = item['MediaSources']
        if len(media_sources) < 1:
            raise ValueError(
                f'Media Source does not have any paths {media_details}')
        elif len(media_sources) > 1:
            raise ValueError(
                f'Media Source has multiple paths {media_details}')
        return media_sources[0]['Path']

    # ------------------------------------------------------------------ #
    #  Auth
    # ------------------------------------------------------------------ #

    @property
    def _header(self) -> dict[str, str]:
        return {
            "Authorization": f"MediaBrowser Token=\"{self.api_key}\""
        }
