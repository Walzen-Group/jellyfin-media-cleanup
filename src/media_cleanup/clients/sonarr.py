from typing import TypedDict
import requests

from media_cleanup.schema.sonarr_schema import Season, Series, EpisodeFileResource

class Result(TypedDict):
    metadata: Series
    original_path: str
    season: int


class SonarrClient:
    def __init__(self, root_url: str, api_key: str) -> None:
        self.root_url = root_url
        self.api_key = api_key

    def get_file_path(self, file_paths: list[int]) -> list[str]:
        res = requests.get(
            f'{self.root_url}/api/v3/series', headers=self._header)
        res.raise_for_status()
        series_list = res.json()

        matching_series: list[dict] = [
            {
                "metadata": series,
                "original_path": file_path,
            }
            for series in series_list
            for file_path in file_paths
            if series["path"] in file_path
        ]

        series_dict = {
            series["metadata"]["id"]: series
            for series in matching_series
        }

        for series_id, series in series_dict.items():
            res = requests.get(
                f"{self.root_url}/api/v3/episodefile?seriesId={series_id}", headers=self._header)
            res.raise_for_status()
            episodes: list[EpisodeFileResource] = res.json()
            matched_episodes = [episode for episode in episodes if episode["path"] == series["original_path"]]
            if matched_episodes:
                matched_episode: EpisodeFileResource = matched_episodes[0]
                series_dict[series_id]["season"] = matched_episode["seasonNumber"]

        return series_dict

    @property
    def _header(self):
        return {
            "X-Api-Key": self.api_key
        }
