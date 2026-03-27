"""
Playground script for testing Sonarr/Radarr deletion methods.

Safe by default: runs in dry-run mode unless --no-dry-run is passed.
Supports lookup by ID or by title search (--title).

Usage:
    # Look up by title (fuzzy search, picks best match)
    uv run python scripts/test_deletion.py --mode delete-movie --title "inception"
    uv run python scripts/test_deletion.py --mode delete-series --title "breaking bad"
    uv run python scripts/test_deletion.py --mode clean-season --title "breaking bad" --season 2

    # Look up by ID
    uv run python scripts/test_deletion.py --mode delete-movie --radarr-id 123
    uv run python scripts/test_deletion.py --mode delete-series --sonarr-id 456
    uv run python scripts/test_deletion.py --mode clean-season --sonarr-id 456 --season 2

    # Actually execute (pass --no-dry-run)
    uv run python scripts/test_deletion.py --mode delete-movie --title "inception" --no-dry-run
"""

import argparse
import sys

from rich.console import Console
from rich.table import Table

from media_cleanup.config import load_config
from media_cleanup.clients.radarr import RadarrClient
from media_cleanup.clients.sonarr import SonarrClient
from media_cleanup.schema.radarr_schema import Movie
from media_cleanup.schema.sonarr_schema import Series, EpisodeFileResource

from rapidfuzz import fuzz, process
import questionary

console = Console()


def _format_size(size_bytes: int) -> str:
    """Format bytes into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    else:
        return f"{size_bytes / 1024 ** 3:.2f} GB"


def _find_movie(radarr: RadarrClient, movie_id: int) -> Movie | None:
    """Find a movie by ID from the Radarr library."""
    movies = radarr.get_all_movies()
    for m in movies:
        if m.id == movie_id:
            return m
    return None


def _find_movie_by_title(radarr: RadarrClient, title: str) -> Movie | None:
    """Find a movie by fuzzy title search. Shows top matches and picks the best."""
    movies = radarr.get_all_movies()
    titles = [m.title for m in movies]
    results = process.extract(title, titles, scorer=fuzz.token_sort_ratio, limit=5)

    if not results or results[0][1] < 60:
        console.print(f"[red]No movies matching '{title}' found in Radarr.[/red]")
        return None

    console.print(f"\n[bold]Search results for '[cyan]{title}[/cyan]':[/bold]")
    table = Table()
    table.add_column("#", style="dim", width=3)
    table.add_column("Title")
    table.add_column("Year", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("ID", style="dim", justify="right")
    choices = []
    for i, (match_title, score, idx) in enumerate(results):
        m = movies[idx]
        table.add_row(str(i + 1), match_title, str(m.year), f"{score:.0f}", str(m.id))
        choices.append(questionary.Choice(
            title=f"{match_title} ({m.year}) [ID: {m.id}]",
            value=idx,
        ))
    console.print(table)

    answer = questionary.select(
        "Select a movie:",
        choices=choices,
    ).ask()
    if answer is None:
        console.print("[red]Cancelled.[/red]")
        sys.exit(0)
    selected = movies[answer]
    console.print(f"\n[green]Selected:[/green] {selected.title} (ID: {selected.id})\n")
    return selected


def _find_series(sonarr: SonarrClient, series_id: int) -> Series | None:
    """Find a series by ID from the Sonarr library."""
    all_series = sonarr.get_all_series()
    for s in all_series:
        if s.id == series_id:
            return s
    return None


def _find_series_by_title(sonarr: SonarrClient, title: str) -> Series | None:
    """Find a series by fuzzy title search. Shows top matches and picks the best."""
    all_series = sonarr.get_all_series()
    titles = [s.title for s in all_series]
    results = process.extract(title, titles, scorer=fuzz.token_sort_ratio, limit=5)

    if not results or results[0][1] < 60:
        console.print(f"[red]No series matching '{title}' found in Sonarr.[/red]")
        return None

    console.print(f"\n[bold]Search results for '[cyan]{title}[/cyan]':[/bold]")
    table = Table()
    table.add_column("#", style="dim", width=3)
    table.add_column("Title")
    table.add_column("Year", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("ID", style="dim", justify="right")
    choices = []
    for i, (match_title, score, idx) in enumerate(results):
        s = all_series[idx]
        table.add_row(str(i + 1), match_title, str(s.year), f"{score:.0f}", str(s.id))
        choices.append(questionary.Choice(
            title=f"{match_title} ({s.year}) [ID: {s.id}]",
            value=idx,
        ))
    console.print(table)

    answer = questionary.select(
        "Select a series:",
        choices=choices,
    ).ask()
    if answer is None:
        console.print("[red]Cancelled.[/red]")
        sys.exit(0)
    selected = all_series[answer]
    console.print(f"\n[green]Selected:[/green] {selected.title} (ID: {selected.id})\n")
    return selected


def _print_movie(movie: Movie) -> None:
    """Display movie details."""
    console.print(f"\n[bold cyan]Movie:[/bold cyan] {movie.title} ({movie.year})")
    console.print(f"  ID:   {movie.id}")
    console.print(f"  Path: {movie.path}")
    console.print(f"  Size: {_format_size(movie.size_on_disk)}")
    console.print(f"  File: {movie.movie_file.relative_path if movie.movie_file else 'N/A'}")
    console.print()


def _print_series(series: Series) -> None:
    """Display series details."""
    console.print(f"\n[bold cyan]Series:[/bold cyan] {series.title} ({series.year})")
    console.print(f"  ID:       {series.id}")
    console.print(f"  Path:     {series.path}")
    console.print(f"  Seasons:  {len(series.seasons)}")
    console.print(f"  Size:     {_format_size(series.statistics.size_on_disk)}")
    console.print()


def _print_episode_files(files: list[EpisodeFileResource]) -> None:
    """Display episode files in a table."""
    table = Table(title="Episode Files")
    table.add_column("ID", style="dim")
    table.add_column("Season", justify="center")
    table.add_column("Path")
    table.add_column("Size", justify="right")

    total_size = 0
    for f in files:
        table.add_row(
            str(f.id),
            str(f.season_number),
            f.relative_path or "(unknown)",
            _format_size(f.size),
        )
        total_size += f.size

    console.print(table)
    console.print(f"  Total: {len(files)} files, {_format_size(total_size)}\n")


def handle_delete_movie(radarr: RadarrClient, movie_id: int, dry_run: bool) -> None:
    """Show movie details and delete it (or show what would happen)."""
    movie = _find_movie(radarr, movie_id)
    if movie is None:
        console.print(f"[red]Movie with ID {movie_id} not found in Radarr.[/red]")
        sys.exit(1)

    _print_movie(movie)

    if dry_run:
        console.print("[yellow][DRY RUN] Would delete this movie and its files.[/yellow]")
    else:
        console.print("[bold red]Deleting movie and files...[/bold red]")
        radarr.delete_movie(movie_id, delete_files=True)
        console.print("[green]Done. Movie deleted.[/green]")


def handle_delete_series(sonarr: SonarrClient, series_id: int, dry_run: bool) -> None:
    """Show series details and delete it (or show what would happen)."""
    series = _find_series(sonarr, series_id)
    if series is None:
        console.print(f"[red]Series with ID {series_id} not found in Sonarr.[/red]")
        sys.exit(1)

    _print_series(series)

    if dry_run:
        console.print("[yellow][DRY RUN] Would delete this series and all its files.[/yellow]")
    else:
        console.print("[bold red]Deleting series and all files...[/bold red]")
        sonarr.delete_series(series_id, delete_files=True)
        console.print("[green]Done. Series deleted.[/green]")


def handle_clean_season(
    sonarr: SonarrClient, series_id: int, season_number: int, dry_run: bool
) -> None:
    """Show season episode files, delete them, and unmonitor the season."""
    series = _find_series(sonarr, series_id)
    if series is None:
        console.print(f"[red]Series with ID {series_id} not found in Sonarr.[/red]")
        sys.exit(1)

    _print_series(series)
    console.print(f"[bold]Target: Season {season_number}[/bold]\n")

    files = sonarr.get_episode_files(series_id, season_number=season_number)
    if not files:
        console.print(f"[yellow]No episode files found for season {season_number}.[/yellow]")
        return

    _print_episode_files(files)

    if dry_run:
        console.print(
            f"[yellow][DRY RUN] Would delete {len(files)} episode file(s) "
            f"and unmonitor season {season_number}.[/yellow]"
        )
    else:
        file_ids = [f.id for f in files]
        console.print(f"[bold red]Deleting {len(files)} episode file(s)...[/bold red]")
        sonarr.delete_episode_files_bulk(file_ids)
        console.print("[green]Files deleted.[/green]")

        console.print(f"[bold]Unmonitoring season {season_number}...[/bold]")
        sonarr.unmonitor_season(series_id, season_number)
        console.print("[green]Season unmonitored. Done.[/green]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test Sonarr/Radarr deletion methods against real instances."
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["delete-movie", "delete-series", "clean-season"],
        help="Which operation to test.",
    )
    parser.add_argument("--radarr-id", type=int, help="Radarr movie ID (for delete-movie).")
    parser.add_argument("--sonarr-id", type=int, help="Sonarr series ID (for delete-series, clean-season).")
    parser.add_argument("--title", type=str, help="Fuzzy title search (alternative to --radarr-id/--sonarr-id).")
    parser.add_argument("--season", type=int, help="Season number (for clean-season).")
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Dry run (default: True). Pass --no-dry-run to execute.",
    )
    args = parser.parse_args()

    cfg = load_config()

    if args.dry_run:
        console.print("[bold yellow]--- DRY RUN MODE ---[/bold yellow]\n")
    else:
        console.print("[bold red]--- LIVE MODE - CHANGES WILL BE APPLIED ---[/bold red]\n")

    if args.mode == "delete-movie":
        radarr = RadarrClient(cfg.radarr_url, cfg.radarr_api_key)
        if args.title:
            movie = _find_movie_by_title(radarr, args.title)
            if movie is None:
                sys.exit(1)
            handle_delete_movie(radarr, movie.id, args.dry_run)
        elif args.radarr_id is not None:
            handle_delete_movie(radarr, args.radarr_id, args.dry_run)
        else:
            parser.error("--radarr-id or --title is required for delete-movie mode.")

    elif args.mode == "delete-series":
        sonarr = SonarrClient(cfg.sonarr_url, cfg.sonarr_api_key)
        if args.title:
            series = _find_series_by_title(sonarr, args.title)
            if series is None:
                sys.exit(1)
            handle_delete_series(sonarr, series.id, args.dry_run)
        elif args.sonarr_id is not None:
            handle_delete_series(sonarr, args.sonarr_id, args.dry_run)
        else:
            parser.error("--sonarr-id or --title is required for delete-series mode.")

    elif args.mode == "clean-season":
        if args.season is None:
            parser.error("--season is required for clean-season mode.")
        sonarr = SonarrClient(cfg.sonarr_url, cfg.sonarr_api_key)
        if args.title:
            series = _find_series_by_title(sonarr, args.title)
            if series is None:
                sys.exit(1)
            handle_clean_season(sonarr, series.id, args.season, args.dry_run)
        elif args.sonarr_id is not None:
            handle_clean_season(sonarr, args.sonarr_id, args.season, args.dry_run)
        else:
            parser.error("--sonarr-id or --title is required for clean-season mode.")


if __name__ == "__main__":
    main()
