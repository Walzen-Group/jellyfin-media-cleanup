"""
Media Cleanup — Stage 1 Orchestrator.

Reads watch history from Jellyfin, cross-references against Sonarr/Radarr
libraries, filters out "keep"-tagged media, applies path + fuzzy matching,
and writes a YAML report of recently vs. not-recently watched media.

Configuration is loaded from a secrets.yaml file in the project root.
"""

import argparse
import sys
import yaml
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from media_cleanup.clients.jellyfin import JellyfinClient
from media_cleanup.clients.sonarr import SonarrClient
from media_cleanup.clients.radarr import RadarrClient
from media_cleanup.matching import (
    match_movies_by_path,
    fuzzy_match_movies,
    build_season_summaries,
    match_seasons_to_sonarr,
)
from media_cleanup.output import generate_report


# Default: media not watched in the last 6 months is flagged
DEFAULT_MONTH_THRESHOLD = 6

# Path to secrets config (expected next to this file's repo root)
SECRETS_PATH = Path(__file__).resolve().parent.parent.parent / "secrets.yaml"

# Force utf-8 on Windows to avoid encoding errors with Rich's unicode characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Shared Rich console instance — force_terminal ensures unicode spinners work on Windows
console = Console(force_terminal=True)


def load_config(path: Path) -> dict:
    """
    Load API credentials and settings from secrets.yaml.

    Expected format:
        jellyfin:
            url: http://...
            api_key: ...
        sonarr:
            url: http://...
            api_key: ...
        radarr:
            url: http://...
            api_key: ...
        settings:
            month_threshold: 6  # optional
    """
    if not path.exists():
        console.print(Panel(
            f"[red]Config file not found at[/red]\n{path}\n\n"
            "Create a [cyan]secrets.yaml[/cyan] with jellyfin/sonarr/radarr credentials.",
            title="Configuration Error",
            border_style="red"
        ))
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _make_progress() -> Progress:
    """Create a Rich progress bar with spinner, description, bar, elapsed time, and ETA."""
    return Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TextColumn("[dim]eta[/dim]"),
        TimeRemainingColumn(),
        console=console,
    )


def _unique_shows(seasons: list) -> int:
    """Count unique series names in a list of SeasonSummary objects."""
    return len({s.series_name for s in seasons})


def _format_size(total_bytes: int) -> str:
    """Format bytes as a human-readable size string (GB or TB)."""
    gb = total_bytes / (1024 ** 3)
    if gb >= 1024:
        return f"{gb / 1024:.1f} TB"
    return f"{gb:.1f} GB"


def _movie_size(matches: list) -> int:
    """Sum size_on_disk across a list of MatchResult objects."""
    return sum(m.size_on_disk for m in matches)


def _season_size(seasons: list) -> int:
    """Sum size_on_disk across a list of SeasonSummary objects."""
    return sum(s.size_on_disk for s in seasons)


def run() -> None:
    """Main orchestration: fetch, match, filter, report."""
    parser = argparse.ArgumentParser(
        prog="media-cleanup",
        description="Jellyfin Media Cleanup — Stage 1: Read & Match",
    )
    parser.add_argument(
        "--mode",
        choices=["all", "movies", "series"],
        default="all",
        help="Run for movies only, series only, or both (default: all)",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=None,
        help=f"Months threshold — media not watched in this many months is flagged (default: {DEFAULT_MONTH_THRESHOLD}, overrides secrets.yaml)",
    )
    args = parser.parse_args()
    mode = args.mode

    console.print(Panel(
        "[bold cyan]Jellyfin Media Cleanup[/bold cyan]\n"
        "Stage 1 — Read & Match",
        border_style="cyan",
    ))

    config = load_config(SECRETS_PATH)
    # CLI --months overrides secrets.yaml setting
    month_threshold = args.months or config.get('settings', {}).get(
        'month_threshold', DEFAULT_MONTH_THRESHOLD)

    mode_label = {"all": "movies + series", "movies": "movies only", "series": "series only"}[mode]
    console.print(f"  Threshold: [yellow]{month_threshold} months[/yellow]")
    console.print(f"  Mode:      [yellow]{mode_label}[/yellow]\n")

    # ----- Initialize clients -----
    jellyfin = JellyfinClient(
        root_url=config['jellyfin']['url'],
        api_key=config['jellyfin']['api_key']
    )

    # Placeholders for results — populated per mode
    recent_movie_matches: list = []
    old_movie_matches: list = []
    kept_movie_matches: list = []
    all_movies: list = []
    recent_seasons_matched: list = []
    old_seasons_matched: list = []
    recent_seasons_unmatched: list = []
    old_seasons_unmatched: list = []
    kept_season_matches: list = []
    all_series: list = []
    recent_seasons: list = []
    old_seasons: list = []
    episodes: list = []
    episode_dates: dict = {}

    # ===== MOVIES =====
    if mode in ("all", "movies"):
        radarr = RadarrClient(
            root_url=config['radarr']['url'],
            api_key=config['radarr']['api_key']
        )

        with _make_progress() as progress:
            task = progress.add_task("Querying Jellyfin movie history", total=2)
            recent_movie_ids = jellyfin.get_recently_watched_movies(month_threshold)
            progress.advance(task)
            old_movie_ids = jellyfin.get_not_recently_watched_movies(month_threshold)
            progress.advance(task)

        with _make_progress() as progress:
            recent_movie_paths = jellyfin.get_file_paths(
                recent_movie_ids, progress, desc="Resolving recent movie paths") if recent_movie_ids else []
            old_movie_paths = jellyfin.get_file_paths(
                old_movie_ids, progress, desc="Resolving old movie paths") if old_movie_ids else []

        with _make_progress() as progress:
            task = progress.add_task("Fetching Radarr library", total=1)
            all_movies = radarr.get_all_movies()
            eligible_movies = radarr.filter_kept_movies(all_movies)
            kept_movies = [m for m in all_movies if m not in eligible_movies]
            progress.advance(task)

        kept_movie_paths = {m.path for m in kept_movies}

        with _make_progress() as progress:
            recent_movie_matches, recent_movie_unmatched = match_movies_by_path(
                recent_movie_paths, all_movies, progress)
            old_movie_matches, old_movie_unmatched = match_movies_by_path(
                old_movie_paths, all_movies, progress)
            recent_movie_matches += fuzzy_match_movies(recent_movie_unmatched, all_movies, progress)
            old_movie_matches += fuzzy_match_movies(old_movie_unmatched, all_movies, progress)

        kept_movie_matches = [m for m in recent_movie_matches + old_movie_matches
                              if m.matched_path in kept_movie_paths]
        recent_movie_matches = [m for m in recent_movie_matches
                                if m.matched_path not in kept_movie_paths]
        old_movie_matches = [m for m in old_movie_matches
                             if m.matched_path not in kept_movie_paths]

    # ===== SERIES =====
    if mode in ("all", "series"):
        sonarr = SonarrClient(
            root_url=config['sonarr']['url'],
            api_key=config['sonarr']['api_key']
        )

        with _make_progress() as progress:
            task = progress.add_task("Querying Jellyfin episode history", total=1)
            episode_dates = jellyfin.get_all_watched_episode_dates()
            progress.advance(task)

        with _make_progress() as progress:
            episodes = jellyfin.get_episode_metadata(episode_dates, progress)

        with _make_progress() as progress:
            task = progress.add_task("Fetching Sonarr library", total=1)
            all_series = sonarr.get_all_series()
            eligible_series = sonarr.filter_kept_series(all_series)
            kept_series = [s for s in all_series if s not in eligible_series]
            progress.advance(task)

        kept_series_paths = {s.path for s in kept_series}

        recent_seasons, old_seasons = build_season_summaries(episodes, month_threshold)

        with _make_progress() as progress:
            recent_seasons_matched, recent_seasons_unmatched = match_seasons_to_sonarr(
                recent_seasons, all_series, progress)
            old_seasons_matched, old_seasons_unmatched = match_seasons_to_sonarr(
                old_seasons, all_series, progress)

        kept_season_matches = [s for s in recent_seasons_matched + old_seasons_matched
                               if s.matched_sonarr_path in kept_series_paths]
        recent_seasons_matched = [s for s in recent_seasons_matched
                                  if s.matched_sonarr_path not in kept_series_paths]
        old_seasons_matched = [s for s in old_seasons_matched
                               if s.matched_sonarr_path not in kept_series_paths]

    # ----- Summary -----
    all_movie_matches = recent_movie_matches + old_movie_matches
    all_seasons_list = recent_seasons_matched + recent_seasons_unmatched + old_seasons_matched + old_seasons_unmatched

    console.print()
    summary = Table(title="Summary", show_header=True, header_style="bold magenta")
    summary.add_column("", style="cyan")
    if mode in ("all", "movies"):
        summary.add_column("Movies", justify="right")
    if mode in ("all", "series"):
        summary.add_column("Shows", justify="right")
        summary.add_column("Seasons", justify="right")
    summary.add_column("Size", justify="right")

    # Watch history
    row: list[str] = ["[bold]Recently watched[/bold]"]
    if mode in ("all", "movies"):
        row.append(f"[green]{len(recent_movie_matches)}[/green]")
    if mode in ("all", "series"):
        row.append(f"[green]{_unique_shows(recent_seasons_matched)}[/green]")
        row.append(f"[green]{len(recent_seasons_matched)}[/green]")
    recent_size = _movie_size(recent_movie_matches) + _season_size(recent_seasons_matched)
    row.append(f"[green]{_format_size(recent_size)}[/green]")
    summary.add_row(*row)

    row = ["[bold]Not recently watched[/bold]"]
    if mode in ("all", "movies"):
        row.append(f"[red]{len(old_movie_matches)}[/red]")
    if mode in ("all", "series"):
        row.append(f"[red]{_unique_shows(old_seasons_matched)}[/red]")
        row.append(f"[red]{len(old_seasons_matched)}[/red]")
    old_size = _movie_size(old_movie_matches) + _season_size(old_seasons_matched)
    row.append(f"[red]{_format_size(old_size)}[/red]")
    summary.add_row(*row)

    # Never watched = library total minus everything that appeared in watch history or kept
    kept_size = _movie_size(kept_movie_matches) + _season_size(kept_season_matches)
    lib_size = sum(m.size_on_disk for m in all_movies) + sum(
        s.statistics.size_on_disk for s in all_series)
    never_watched_size = lib_size - recent_size - old_size - kept_size

    # Count never-watched items: library items that didn't match any watch history entry
    watched_movie_paths = {m.matched_path for m in recent_movie_matches + old_movie_matches + kept_movie_matches if m.matched_path}
    never_watched_movies = [m for m in all_movies if m.path not in watched_movie_paths]

    watched_series_paths = {s.matched_sonarr_path for s in recent_seasons_matched + old_seasons_matched + kept_season_matches if s.matched_sonarr_path}
    never_watched_series = [s for s in all_series if s.path not in watched_series_paths]

    row = ["[bold]Never watched[/bold]"]
    if mode in ("all", "movies"):
        row.append(f"[dim]{len(never_watched_movies)}[/dim]")
    if mode in ("all", "series"):
        row.append(f"[dim]{len(never_watched_series)}[/dim]")
        row.append("")
    row.append(f"[dim]{_format_size(never_watched_size)}[/dim]")
    summary.add_row(*row)

    # Library
    summary.add_section()
    row = ["Library total"]
    if mode in ("all", "movies"):
        row.append(str(len(all_movies)))
    if mode in ("all", "series"):
        row.append(str(len(all_series)))
        row.append("")
    row.append(f"[dim]{_format_size(lib_size)}[/dim]")
    summary.add_row(*row)

    row = ["Kept"]
    if mode in ("all", "movies"):
        row.append(f"[yellow]{len(kept_movie_matches)}[/yellow]")
    if mode in ("all", "series"):
        row.append(f"[yellow]{_unique_shows(kept_season_matches)}[/yellow]")
        row.append(f"[yellow]{len(kept_season_matches)}[/yellow]")
    row.append(f"[yellow]{_format_size(kept_size)}[/yellow]")
    summary.add_row(*row)

    # Matching
    summary.add_section()
    row = ["Matched"]
    if mode in ("all", "movies"):
        row.append(f"[green]{sum(1 for m in all_movie_matches if m.is_matched)}[/green]")
    if mode in ("all", "series"):
        matched_seasons = recent_seasons_matched + old_seasons_matched
        row.append(f"[green]{_unique_shows(matched_seasons)}[/green]")
        row.append(f"[green]{len(matched_seasons)}[/green]")
    row.append("")
    summary.add_row(*row)

    row = ["Ambiguous"]
    if mode in ("all", "movies"):
        row.append(f"[yellow]{sum(1 for m in all_movie_matches if m.is_ambiguous)}[/yellow]")
    if mode in ("all", "series"):
        row.append(f"[yellow]{_unique_shows([s for s in all_seasons_list if s.is_ambiguous])}[/yellow]")
        row.append(f"[yellow]{sum(1 for s in all_seasons_list if s.is_ambiguous)}[/yellow]")
    row.append("")
    summary.add_row(*row)

    row = ["Unmatched"]
    if mode in ("all", "movies"):
        row.append(f"[red]{sum(1 for m in all_movie_matches if not m.is_matched)}[/red]")
    if mode in ("all", "series"):
        unmatched_all = recent_seasons_unmatched + old_seasons_unmatched
        row.append(f"[red]{_unique_shows(unmatched_all)}[/red]")
        row.append(f"[red]{len(unmatched_all)}[/red]")
    row.append("")
    summary.add_row(*row)

    # Episode resolution stats (series mode only)
    if mode in ("all", "series"):
        skipped_episodes = len(episode_dates) - len(episodes)
        fallback_episodes = sum(1 for ep in episodes if ep.season_number == -1)
        if fallback_episodes or skipped_episodes:
            summary.add_section()
        if fallback_episodes:
            row = ["Episodes resolved via name fallback"]
            if mode == "all":
                row.append("")
            row += ["", f"[yellow]{fallback_episodes}[/yellow]", ""]
            summary.add_row(*row)
        if skipped_episodes:
            row = ["Episodes skipped (no data)"]
            if mode == "all":
                row.append("")
            row += ["", f"[dim]{skipped_episodes}[/dim]", ""]
            summary.add_row(*row)

    # Space savings estimates
    summary.add_section()

    # "Seasons only" = sum of per-season sizes for not-recently-watched
    seasons_only_size = _movie_size(old_movie_matches) + _season_size(old_seasons_matched)

    # "Entire shows" = for series with ANY not-recently-watched season,
    # sum the full series size (not just the stale seasons)
    entire_shows_size = _movie_size(old_movie_matches)
    if mode in ("all", "series") and old_seasons_matched:
        series_by_path = {s.path: s for s in all_series}
        old_series_paths = {s.matched_sonarr_path for s in old_seasons_matched if s.matched_sonarr_path}
        entire_shows_size += sum(
            series_by_path[p].statistics.size_on_disk
            for p in old_series_paths if p in series_by_path
        )

    old_show_count = _unique_shows(old_seasons_matched) if mode in ("all", "series") else 0

    row = ["[bold]Savings (seasons only)[/bold]"]
    if mode in ("all", "movies"):
        row.append(f"[red]{len(old_movie_matches)}[/red]")
    if mode in ("all", "series"):
        row.append(f"[red]{old_show_count}[/red]")
        row.append(f"[red]{len(old_seasons_matched)}[/red]")
    row.append(f"[bold red]{_format_size(seasons_only_size)}[/bold red]")
    summary.add_row(*row)

    row = ["[bold]Savings (entire shows)[/bold]"]
    if mode in ("all", "movies"):
        row.append(f"[red]{len(old_movie_matches)}[/red]")
    if mode in ("all", "series"):
        row.append(f"[red]{old_show_count}[/red]")
        row.append("")
    row.append(f"[bold red]{_format_size(entire_shows_size)}[/bold red]")
    summary.add_row(*row)

    console.print(summary)
    console.print()

    # ----- Generate YAML report -----
    output_path = generate_report(
        recently_watched_movies=recent_movie_matches,
        not_recently_watched_movies=old_movie_matches,
        recent_seasons=recent_seasons_matched,
        old_seasons=old_seasons_matched,
        unmatched_seasons=recent_seasons_unmatched + old_seasons_unmatched,
        kept_movie_matches=kept_movie_matches,
        kept_season_matches=kept_season_matches,
        month_threshold=month_threshold,
    )

    console.print(Panel(
        f"[bold green]Report written to:[/bold green] [cyan]{output_path}[/cyan]",
        border_style="green",
    ))


if __name__ == '__main__':
    run()
