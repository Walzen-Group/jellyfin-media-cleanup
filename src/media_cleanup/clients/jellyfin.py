"""
Jellyfin API client.

Queries the Playback Reporting plugin's custom SQL endpoint to find
movies and series based on watch history thresholds. Resolves item IDs
to file paths via the Jellyfin /items endpoint, chunked to avoid URI
length limits.

For series, a single query fetches ALL ever-watched episodes with their
most recent play date. These are then resolved to series/season metadata
and grouped at the season level by the matching module.
"""

import requests as re
from typing import Callable, TypedDict

from media_cleanup.types import EpisodeInfo

# Generic progress callback: (step_name, current, total)
ProgressCallback = Callable[[str, int, int], None]


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

EpisodeItemSchema = TypedDict('EpisodeItemSchema',
                              {
                                  'Id': str,
                                  'Name': str,
                                  'SeriesName': str,
                                  'ParentIndexNumber': int,   # season number
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

    def get_episode_metadata(
        self,
        item_dates: dict[str, dict[str, str]],
        progress_callback: ProgressCallback | None = None,
    ) -> list[EpisodeInfo]:
        """
        Resolve a dict of {item_id: {"last_played": ..., "item_name": ...}}
        to full EpisodeInfo records by fetching series name and season number
        from the Jellyfin items API.

        When an item ID can no longer be resolved (e.g. stale after a library
        re-scan), falls back to the ItemName from PlaybackActivity. These
        fallback entries have season_number=-1 and an empty file_path, but
        still carry the series name so they can reach fuzzy matching.

        Automatically chunks requests to stay under URI length limits.
        """
        ids = list(item_dates.keys())
        chunks = list(range(0, len(ids), self.chunk_length))
        results: list[EpisodeInfo] = []
        resolved_ids: set[str] = set()
        cb = progress_callback or (lambda *_: None)
        resolved_count = 0

        for i in chunks:
            chunk = ids[i:i + self.chunk_length]
            res = re.get(
                f'{self.root_url}/items'
                f'?ids={",".join(chunk)}'
                f'&fields=MediaSources',
                headers=self._header)
            res.raise_for_status()

            returned_ids: set[str] = set()
            for item in res.json().get('Items', []):
                item_id = item.get('Id')
                returned_ids.add(item_id)
                series_name = item.get('SeriesName')
                season_number = item.get('ParentIndexNumber')
                media_sources = item.get('MediaSources', [])

                # Skip episodes missing required metadata — they'll be handled
                # in the fallback pass below
                if not series_name or season_number is None or not media_sources:
                    resolved_count += 1
                    cb(f"Resolving episodes", resolved_count, len(ids))
                    continue

                resolved_ids.add(item_id)
                results.append(EpisodeInfo(
                    item_id=item_id,
                    series_name=series_name,
                    season_number=season_number,
                    file_path=media_sources[0].get('Path', ''),
                    last_played=item_dates[item_id]['last_played'],
                ))

                resolved_count += 1
                # Emit the current show name so callers can display it
                cb(f"Resolving episodes: {series_name}", resolved_count, len(ids))

            # Advance for IDs that the API didn't return (stale/deleted)
            missing_count = len(chunk) - len(returned_ids)
            if missing_count > 0:
                resolved_count += missing_count
                cb(f"Resolving episodes", resolved_count, len(ids))

        # ----- Fallback: use ItemName from PlaybackActivity for unresolved IDs -----
        unresolved_ids = set(ids) - resolved_ids
        fallback_results: list[EpisodeInfo] = []
        fallback_failed = 0
        if unresolved_ids:
            cb("Resolving episodes: name fallback", resolved_count, len(ids))
            for item_id in unresolved_ids:
                info = item_dates[item_id]
                item_name = info.get('item_name', '')
                if not item_name:
                    fallback_failed += 1
                    continue

                series_name, season_number = self._parse_episode_item_name(item_name)
                if not series_name:
                    fallback_failed += 1
                    continue

                fallback_results.append(EpisodeInfo(
                    item_id=item_id,
                    series_name=series_name,
                    season_number=season_number,
                    file_path='',
                    last_played=info['last_played'],
                ))

        results.extend(fallback_results)
        cb("Resolving episodes: done", len(ids), len(ids))

        return results

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
