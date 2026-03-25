"""
Media Cleanup — CLI entry point.

Parses arguments, drives the CleanupService pipeline with Rich progress
bars, renders a summary table, and writes the YAML report. All business
logic lives in the service layer; this module owns only presentation.
"""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from media_cleanup.config import load_config, DEFAULT_MONTH_THRESHOLD
from media_cleanup.service import CleanupService, build_summary
from media_cleanup.output import generate_report


# Path to secrets config (expected next to this file's repo root)
SECRETS_PATH = Path(__file__).resolve().parent.parent.parent / "secrets.yaml"

# Force utf-8 on Windows to avoid encoding errors with Rich's unicode characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Shared Rich console instance — force_terminal ensures unicode spinners work on Windows
console = Console(force_terminal=True)


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

    # ----- Configuration -----
    config = load_config(SECRETS_PATH)
    if not config.jellyfin_url:
        console.print(Panel(
            f"[red]Config file not found or incomplete at[/red]\n{SECRETS_PATH}\n\n"
            "Create a [cyan]secrets.yaml[/cyan] with jellyfin/sonarr/radarr credentials,\n"
            "or set the corresponding environment variables.",
            title="Configuration Error",
            border_style="red"
        ))
        sys.exit(1)

    # CLI --months overrides config
    month_threshold = args.months if args.months is not None else config.month_threshold

    mode_label = {"all": "movies + series", "movies": "movies only", "series": "series only"}[mode]
    console.print(f"  Threshold: [yellow]{month_threshold} months[/yellow]")
    console.print(f"  Mode:      [yellow]{mode_label}[/yellow]\n")

    # ----- Run the pipeline with Rich progress -----
    _active_progress: dict = {}

    def _step_base(step: str) -> str:
        """Extract base step name, e.g. 'Resolving episodes: Billions' -> 'Resolving episodes'."""
        return step.split(":")[0].rstrip()

    def rich_progress_callback(step: str, current: int, total: int) -> None:
        """Translate service progress events into Rich progress bar updates."""
        p = _active_progress.get("progress")
        if p is None:
            return
        task_id = _active_progress.get("task")
        prev_base = _active_progress.get("base")
        cur_base = _step_base(step)

        if task_id is None or prev_base != cur_base:
            # New base step — finish previous task, create new one
            if task_id is not None:
                p.update(task_id, completed=p.tasks[task_id].total)
            task_id = p.add_task(step, total=max(total, 1))
            _active_progress["task"] = task_id
            _active_progress["base"] = cur_base
        # Update description (shows current show name) and progress
        p.update(task_id, description=step, completed=current, total=max(total, 1))

    service = CleanupService(config)

    with _make_progress() as progress:
        _active_progress["progress"] = progress
        result = service.run_analysis(
            mode=mode,
            month_threshold=month_threshold,
            progress_callback=rich_progress_callback,
        )
        # Ensure last task shows complete
        task_id = _active_progress.get("task")
        if task_id is not None:
            progress.update(task_id, completed=progress.tasks[task_id].total)

    # ----- Summary -----
    s = build_summary(result, mode)

    console.print()
    summary = Table(title="Summary", show_header=True, header_style="bold magenta")
    summary.add_column("", style="cyan")
    if mode in ("all", "movies"):
        summary.add_column("Movies", justify="right")
    if mode in ("all", "series"):
        summary.add_column("Shows", justify="right")
        summary.add_column("Seasons", justify="right")
    summary.add_column("Size", justify="right")

    # Recently watched
    row: list[str] = ["[bold]Recently watched[/bold]"]
    if mode in ("all", "movies"):
        row.append(f"[green]{s['recent_movie_count']}[/green]")
    if mode in ("all", "series"):
        row.append(f"[green]{s['recent_shows_count']}[/green]")
        row.append(f"[green]{s['recent_seasons_count']}[/green]")
    row.append(f"[green]{s['recent_size_fmt']}[/green]")
    summary.add_row(*row)

    # Not recently watched
    row = ["[bold]Not recently watched[/bold]"]
    if mode in ("all", "movies"):
        row.append(f"[red]{s['old_movie_count']}[/red]")
    if mode in ("all", "series"):
        row.append(f"[red]{s['old_shows_count']}[/red]")
        row.append(f"[red]{s['old_seasons_count']}[/red]")
    size_label = f"[red]{s['old_size_fmt']}[/red]"
    if s['entire_shows_size'] > s['old_size']:
        size_label += f"\n[dim]{s['entire_shows_size_fmt']} total[/dim]"
    row.append(size_label)
    summary.add_row(*row)

    # Never watched
    row = ["[bold]Never watched[/bold]"]
    if mode in ("all", "movies"):
        row.append(f"[dim]{s['never_watched_movie_count']}[/dim]")
    if mode in ("all", "series"):
        row.append(f"[dim]{s['never_watched_series_count']}[/dim]")
        row.append("")
    row.append(f"[dim]{s['never_watched_size_fmt']}[/dim]")
    summary.add_row(*row)

    # Library
    summary.add_section()
    row = ["Library total"]
    if mode in ("all", "movies"):
        row.append(str(s['library_movie_count']))
    if mode in ("all", "series"):
        row.append(str(s['library_series_count']))
        row.append("")
    row.append(f"[dim]{s['lib_size_fmt']}[/dim]")
    summary.add_row(*row)

    row = ["Kept"]
    if mode in ("all", "movies"):
        row.append(f"[yellow]{s['kept_movie_count']}[/yellow]")
    if mode in ("all", "series"):
        row.append(f"[yellow]{s['kept_shows_count']}[/yellow]")
        row.append(f"[yellow]{s['kept_seasons_count']}[/yellow]")
    row.append(f"[yellow]{s['kept_size_fmt']}[/yellow]")
    summary.add_row(*row)

    # Matching
    summary.add_section()
    row = ["Matched"]
    if mode in ("all", "movies"):
        row.append(f"[green]{s['matched_movie_count']}[/green]")
    if mode in ("all", "series"):
        row.append(f"[green]{s['matched_shows_count']}[/green]")
        row.append(f"[green]{s['matched_seasons_count']}[/green]")
    row.append("")
    summary.add_row(*row)

    row = ["Ambiguous"]
    if mode in ("all", "movies"):
        row.append(f"[yellow]{s['ambiguous_movie_count']}[/yellow]")
    if mode in ("all", "series"):
        row.append(f"[yellow]{s['ambiguous_shows_count']}[/yellow]")
        row.append(f"[yellow]{s['ambiguous_seasons_count']}[/yellow]")
    row.append("")
    summary.add_row(*row)

    row = ["Unmatched"]
    if mode in ("all", "movies"):
        row.append(f"[red]{s['unmatched_movie_count']}[/red]")
    if mode in ("all", "series"):
        row.append(f"[red]{s['unmatched_shows_count']}[/red]")
        row.append(f"[red]{s['unmatched_seasons_count']}[/red]")
    row.append("")
    summary.add_row(*row)

    # Episode resolution stats
    if mode in ("all", "series"):
        if s['fallback_episodes'] or s['skipped_episodes']:
            summary.add_section()
        if s['fallback_episodes']:
            row = ["Episodes resolved via name fallback"]
            if mode == "all":
                row.append("")
            row += ["", f"[yellow]{s['fallback_episodes']}[/yellow]", ""]
            summary.add_row(*row)
        if s['skipped_episodes']:
            row = ["Episodes skipped (no data)"]
            if mode == "all":
                row.append("")
            row += ["", f"[dim]{s['skipped_episodes']}[/dim]", ""]
            summary.add_row(*row)

    console.print(summary)
    console.print()

    # ----- Generate YAML report -----
    output_path = generate_report(
        recently_watched_movies=result.recent_movie_matches,
        not_recently_watched_movies=result.old_movie_matches,
        recent_seasons=result.recent_seasons_matched,
        old_seasons=result.old_seasons_matched,
        unmatched_seasons=result.recent_seasons_unmatched + result.old_seasons_unmatched,
        kept_movie_matches=result.kept_movie_matches,
        kept_season_matches=result.kept_season_matches,
        month_threshold=month_threshold,
    )

    console.print(Panel(
        f"[bold green]Report written to:[/bold green] [cyan]{output_path}[/cyan]",
        border_style="green",
    ))


if __name__ == '__main__':
    run()
