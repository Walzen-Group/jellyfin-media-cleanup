"""
Media Cleanup — Stage 1 Orchestrator.

Reads watch history from Jellyfin, cross-references against Sonarr/Radarr
libraries, filters out "keep"-tagged media, applies path + fuzzy matching,
and writes a YAML report of recently vs. not-recently watched media.

Configuration is loaded from a secrets.yaml file in the project root.
"""

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

# Shared Rich console instance
console = Console()


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


def run() -> None:
    """Main orchestration: fetch, match, filter, report."""
    console.print(Panel(
        "[bold cyan]Jellyfin Media Cleanup[/bold cyan]\n"
        "Stage 1 — Read & Match",
        border_style="cyan",
    ))

    config = load_config(SECRETS_PATH)
    month_threshold = config.get('settings', {}).get(
        'month_threshold', DEFAULT_MONTH_THRESHOLD)

    console.print(f"  Threshold: [yellow]{month_threshold} months[/yellow]\n")

    # ----- Initialize clients -----
    jellyfin = JellyfinClient(
        root_url=config['jellyfin']['url'],
        api_key=config['jellyfin']['api_key']
    )
    sonarr = SonarrClient(
        root_url=config['sonarr']['url'],
        api_key=config['sonarr']['api_key']
    )
    radarr = RadarrClient(
        root_url=config['radarr']['url'],
        api_key=config['radarr']['api_key']
    )

    # ----- Step 1: Fetch Jellyfin watch history -----
    with _make_progress() as progress:
        task = progress.add_task("Querying Jellyfin watch history", total=3)

        recent_movie_ids = jellyfin.get_recently_watched_movies(month_threshold)
        progress.advance(task)

        old_movie_ids = jellyfin.get_not_recently_watched_movies(month_threshold)
        progress.advance(task)

        # Single query for all ever-watched episodes + their last-played dates
        episode_dates = jellyfin.get_all_watched_episode_dates()
        progress.advance(task)

    # ----- Step 2: Resolve movie IDs to file paths -----
    with _make_progress() as progress:
        recent_movie_paths = jellyfin.get_file_paths(
            recent_movie_ids, progress, desc="Resolving recent movie paths") if recent_movie_ids else []
        old_movie_paths = jellyfin.get_file_paths(
            old_movie_ids, progress, desc="Resolving old movie paths") if old_movie_ids else []

    # ----- Step 3: Resolve episode metadata (series name + season number) -----
    with _make_progress() as progress:
        episodes = jellyfin.get_episode_metadata(episode_dates, progress)

    # ----- Step 4: Fetch arr libraries + filter "keep" tags -----
    with _make_progress() as progress:
        task = progress.add_task("Fetching Radarr/Sonarr libraries", total=2)

        all_movies = radarr.get_all_movies()
        eligible_movies = radarr.filter_kept_movies(all_movies)
        kept_movies = [m for m in all_movies if m not in eligible_movies]
        progress.advance(task)

        all_series = sonarr.get_all_series()
        eligible_series = sonarr.filter_kept_series(all_series)
        kept_series = [s for s in all_series if s not in eligible_series]
        progress.advance(task)

    # Build sets of kept paths for post-match classification
    kept_movie_paths = {m.get('path', '') for m in kept_movies}
    kept_series_paths = {s.get('path', '') for s in kept_series}

    # ----- Step 5: Match movies against ALL movies (including kept) -----
    with _make_progress() as progress:
        recent_movie_matches, recent_movie_unmatched = match_movies_by_path(
            recent_movie_paths, all_movies, progress)
        old_movie_matches, old_movie_unmatched = match_movies_by_path(
            old_movie_paths, all_movies, progress)

        recent_movie_matches += fuzzy_match_movies(recent_movie_unmatched, all_movies, progress)
        old_movie_matches += fuzzy_match_movies(old_movie_unmatched, all_movies, progress)

    # ----- Step 6: Build season summaries + match to Sonarr (all series) -----
    recent_seasons, old_seasons = build_season_summaries(episodes, month_threshold)

    with _make_progress() as progress:
        recent_seasons_matched, recent_seasons_unmatched = match_seasons_to_sonarr(
            recent_seasons, all_series, progress)
        old_seasons_matched, old_seasons_unmatched = match_seasons_to_sonarr(
            old_seasons, all_series, progress)

    # ----- Split matched results into eligible vs kept -----
    # Movies matched to a kept path go in the keep bucket, not recently/not-recently
    kept_movie_matches = [m for m in recent_movie_matches + old_movie_matches
                          if m.matched_path in kept_movie_paths]
    recent_movie_matches = [m for m in recent_movie_matches
                            if m.matched_path not in kept_movie_paths]
    old_movie_matches = [m for m in old_movie_matches
                         if m.matched_path not in kept_movie_paths]

    # Seasons matched to a kept series path go in the keep bucket
    kept_season_matches = [s for s in recent_seasons_matched + old_seasons_matched
                           if s.matched_sonarr_path in kept_series_paths]
    recent_seasons_matched = [s for s in recent_seasons_matched
                              if s.matched_sonarr_path not in kept_series_paths]
    old_seasons_matched = [s for s in old_seasons_matched
                           if s.matched_sonarr_path not in kept_series_paths]

    # ----- Summary -----
    all_movie_matches = recent_movie_matches + old_movie_matches
    all_seasons = recent_seasons_matched + recent_seasons_unmatched + old_seasons_matched + old_seasons_unmatched
    # Episodes with no usable data at all (no API resolution AND no ItemName fallback)
    skipped_episodes = len(episode_dates) - len(episodes)
    # Episodes that used the ItemName fallback (stale IDs)
    fallback_episodes = sum(1 for ep in episodes if ep.season_number == -1)

    console.print()
    summary = Table(title="Summary", show_header=True, header_style="bold magenta")
    summary.add_column("", style="cyan")
    summary.add_column("Movies", justify="right")
    summary.add_column("Seasons", justify="right")

    # Watch history
    summary.add_row(
        "[bold]Recently watched[/bold]",
        f"[green]{len(recent_movie_matches)}[/green]",
        f"[green]{len(recent_seasons)}[/green]",
    )
    summary.add_row(
        "[bold]Not recently watched[/bold]",
        f"[red]{len(old_movie_matches)}[/red]",
        f"[red]{len(old_seasons)}[/red]",
    )

    # Library
    summary.add_section()
    summary.add_row(
        "Library total",
        str(len(all_movies)),
        str(len(all_series)),
    )
    summary.add_row(
        "Kept",
        f"[yellow]{len(kept_movie_matches)}[/yellow]",
        f"[yellow]{len(kept_season_matches)}[/yellow]",
    )

    # Matching
    summary.add_section()
    summary.add_row(
        "Matched",
        f"[green]{sum(1 for m in all_movie_matches if m.is_matched)}[/green]",
        f"[green]{len(recent_seasons_matched) + len(old_seasons_matched)}[/green]",
    )
    summary.add_row(
        "Ambiguous",
        f"[yellow]{sum(1 for m in all_movie_matches if m.is_ambiguous)}[/yellow]",
        f"[yellow]{sum(1 for s in all_seasons if s.is_ambiguous)}[/yellow]",
    )
    summary.add_row(
        "Unmatched",
        f"[red]{sum(1 for m in all_movie_matches if not m.is_matched)}[/red]",
        f"[red]{len(recent_seasons_unmatched) + len(old_seasons_unmatched)}[/red]",
    )

    # Episode resolution stats
    if fallback_episodes or skipped_episodes:
        summary.add_section()
    if fallback_episodes:
        summary.add_row(
            "Episodes resolved via name fallback",
            "",
            f"[yellow]{fallback_episodes}[/yellow]",
        )
    if skipped_episodes:
        summary.add_row(
            "Episodes skipped (no data)",
            "",
            f"[dim]{skipped_episodes}[/dim]",
        )

    console.print(summary)
    console.print()

    # ----- Step 7: Generate YAML report -----
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
