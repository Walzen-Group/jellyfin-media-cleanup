import requests

from media_cleanup.schema.sonarr_schema import Series, EpisodeFile


class SonarrClient:
    def __init__(self, root_url: str, api_key: str) -> None:
        self.root_url = root_url
        self.api_key = api_key

    def get_file_path(self, file_paths: list[int]) -> list[str]:
        res = requests.get(f'{self.root_url}/api/v3/series', headers=self._header)
        res.raise_for_status()
        series_list = res.json()

        matching_series: list[Series] = [series for series in series_list
            if any(series["path"] in file_path for file_path in file_paths)]

        # todo put
        series_dict = {
            series['id']: {
                "metadata": series,
                "original_path": series["path"],
            }
            for series in matching_series
        }


        for series_id, series in series_dict.items():
            res = requests.get(f"{self.root_url}/api/v3/episodefile?seriesId={series_id}", headers=self._header)
            res.raise_for_status()
            episodes: list[EpisodeFile] = res.json()
            for episode in episodes:
                file_name = series["original_path"].replace(series["metadata"]["path"], "")

                pass


        return matching_series

    @property
    def _header(self):
        return {
            "X-Api-Key": self.api_key
        }
