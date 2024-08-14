import requests as re
from typing import TypedDict


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
                                       "colums": list[str], # yes there is a typo in the plugin api
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


    def get_recently_watched_movies(self, month_count: int) -> list[str]:
        res = re.post(f'{self.root_url}/user_usage_stats/submit_custom_query?stamp=1723648897090',  # TODO parametrize timestamp
                      headers=self._header,
                      json={"CustomQueryString": ("SELECT * \nFROM  PlaybackActivity \n"
                                                  f"WHERE PlayDuration > 200 AND DateCreated < date('now','-{month_count} month') AND ItemType like 'Movie' \n"
                                                  "GROUP BY ItemId \n"
                                                  "ORDER BY DateCreated DESC \n\t\t\t"),
                            "ReplaceUserId": True
                            })
        res.raise_for_status()
        res: PlaybackResponseSchema = res.json()
        item_id_column_number = res['colums'].index('ItemId')
        return [r[item_id_column_number] for r in res["results"]]

    def get_file_paths(self, ids: list[str]) -> list[str]:
        results = []
        for i in range(0, len(ids), self.chunk_length):
            results.extend(self._get_file_paths_for_chunk_length(ids[i:i+self.chunk_length]))
        return results

    def _get_file_paths_for_chunk_length(self, ids: list[str]) -> list[str]:
        if len(ids) > self.chunk_length:
            raise ValueError('request URI will be too large with this many ids')
        res = re.get(
            f'{self.root_url}/items?ids={",".join(ids)}&fields=MediaSources', headers=self._header)
        res.raise_for_status()
        return [self._get_item_path(item) for item in res.json()['Items']]

    def _get_item_path(self, item: ItemResponseSchema) -> str:
        media_details = f"{item['Id']} {item['MediaSources']}"
        media_sources = item['MediaSources']
        if len(media_sources) < 1:
            raise ValueError(
                f'Media Source does not have any paths {media_details}')
        elif len(media_sources) > 1:
            raise ValueError(
                f'Media Source has multiple paths {media_details}')
        return media_sources[0]['Path']

    @property
    def _header(self):
        return {
            "Authorization": f"MediaBrowser Token=\"{self.api_key}\""
        }
