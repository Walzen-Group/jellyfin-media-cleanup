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
from media_cleanup.models import build_summary
from media_cleanup.service import CleanupService, get_pipeline_steps, MOVIE_STEPS, SERIES_STEPS
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
    """Create a Rich progress bar with spinner, description, bar, elapsed time, ETA, and trailing subtitle."""
    return Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TextColumn("[dim]eta[/dim]"),
        TimeRemainingColumn(),
        TextColumn("{task.fields[subtitle]}"),
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
    parser.add_argument(
        "--added-threshold",
        type=int,
        default=12,
        help="Never-watched items added within this many months are shown as 'New (unwatched)' rather than cleanup candidates (default: 12)",
    )
    parser.add_argument(
        "--precise-matching",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Resolve all episodes for path matching (slower, correctly handles same series in multiple Jellyfin libraries). Use --no-precise-matching for faster one-rep-per-show mode (default: on)",
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

    precise_matching: bool = args.precise_matching
    mode_label = {"all": "movies + series", "movies": "movies only", "series": "series only"}[mode]
    console.print(f"  Threshold: [yellow]{month_threshold} months[/yellow]")
    console.print(f"  Mode:      [yellow]{mode_label}[/yellow]")
    if mode in ("all", "series"):
        console.print(f"  Matching:  [yellow]{'precise' if precise_matching else 'fast (one rep per show)'}[/yellow]")
    console.print()

    # ----- Run the pipeline with Rich progress -----
    step_offsets, _total_weight = get_pipeline_steps(mode, precise_matching)

    # Map each step name to its group ("movies" or "series")
    _movie_names = [name for name, _ in MOVIE_STEPS]
    _series_names = [name for name, _ in SERIES_STEPS]
    def _group_of(base: str) -> str:
        if base in _movie_names:
            return "movies"
        if base in _series_names:
            return "series"
        return base  # unknown — treat as its own group

    _state: dict = {}  # keys: group, p, task_ids {step_name: task_id}, current_base

    _GROUP_LABELS = {"movies": "Movies", "series": "TV Shows"}

    def rich_progress_callback(step: str, global_current: int, _global_total: int) -> None:
        """One Progress per group (movies / series); tasks are pre-added hidden
        and revealed one-by-one as they arrive.  The description column is
        always the fixed step label, so bar widths never shift.  The show name
        trails after the ETA.
        """
        base = step.split(":")[0].rstrip()
        step_offset, step_weight = step_offsets.get(base, (0, max(_global_total, 1)))
        group = _group_of(base)

        # Group transition: stop old Progress, print header, start new one with all tasks hidden
        if _state.get("group") != group:
            prev_p = _state.get("p")
            if prev_p is not None:
                for sname, tid in _state["task_ids"].items():
                    _, sw = step_offsets.get(sname, (0, 1))
                    prev_p.update(tid, completed=sw, visible=True)
                prev_p.stop()
            label = _GROUP_LABELS.get(group, group)
            console.print(f"\n[bold]{label}[/bold]")
            group_steps = _movie_names if group == "movies" else _series_names
            p = _make_progress()
            p.start()
            task_ids = {
                sname: p.add_task(sname, total=step_offsets.get(sname, (0, 1))[1], subtitle="", completed=0, visible=False)
                for sname in group_steps
            }
            _state.update({"group": group, "p": p, "task_ids": task_ids, "current_base": None})

        # Step transition within the same group: mark old task complete, reveal new one
        if _state.get("current_base") != base:
            old_base = _state.get("current_base")
            if old_base and old_base in _state["task_ids"]:
                _, old_weight = step_offsets.get(old_base, (0, 1))
                _state["p"].update(_state["task_ids"][old_base], completed=old_weight, visible=True)
            _state["current_base"] = base
            _state["p"].update(_state["task_ids"][base], visible=True)

        p = _state["p"]
        task_id = _state["task_ids"][base]
        local_current = max(0, global_current - step_offset)

        # Show name trails after the ETA; only update when the step carries one
        kwargs: dict = {"completed": local_current}
        if ":" in step:
            kwargs["subtitle"] = step.split(":", 1)[1].strip()
        p.update(task_id, **kwargs)

    service = CleanupService(config)
    result = service.run_analysis(
        mode=mode,
        month_threshold=month_threshold,
        precise_matching=precise_matching,
        progress_callback=rich_progress_callback,
    )
    # Finalise the last group's Progress
    if _state.get("p") is not None:
        for sname, tid in _state["task_ids"].items():
            _, sw = step_offsets.get(sname, (0, 1))
            _state["p"].update(tid, completed=sw, visible=True)
        _state["p"].stop()

    # ----- Summary -----
    added_threshold: int = args.added_threshold
    s = build_summary(result, mode, added_threshold)

    console.print()
    summary = Table(title="Summary", show_header=True, header_style="bold magenta")
    summary.add_column("", style="cyan")
    if mode in ("all", "movies"):
        summary.add_column("Movies", justify="right")
    if mode in ("all", "series"):
        summary.add_column("Shows", justify="right")
        summary.add_column("Seasons", justify="right")
    if mode in ("all", "movies"):
        summary.add_column("Movie Size", justify="right")
    if mode in ("all", "series"):
        summary.add_column("Series Size", justify="right")
        summary.add_column("Series Size (Greedy)", justify="right")

    # Recently watched
    row: list[str] = ["[bold]Recently watched[/bold]"]
    if mode in ("all", "movies"):
        row.append(f"[green]{s.recent.movie_count}[/green]")
    if mode in ("all", "series"):
        row.append(f"[green]{s.recent.shows_count}[/green]")
        row.append(f"[green]{s.recent.seasons_count}[/green]")
    if mode in ("all", "movies"):
        row.append(f"[green]{s.recent.movie_size_fmt}[/green]")
    if mode in ("all", "series"):
        row.append(f"[green]{s.recent.series_size_fmt}[/green]")
        row.append(f"[green]{s.recent.series_size_greedy_fmt}[/green]")
    summary.add_row(*row)

    # Not recently watched
    row = ["[bold]Not recently watched[/bold]"]
    if mode in ("all", "movies"):
        row.append(f"[red]{s.old.movie_count}[/red]")
    if mode in ("all", "series"):
        row.append(f"[red]{s.old.shows_count}[/red]")
        row.append(f"[red]{s.old.seasons_count}[/red]")
    if mode in ("all", "movies"):
        row.append(f"[red]{s.old.movie_size_fmt}[/red]")
    if mode in ("all", "series"):
        row.append(f"[red]{s.old.series_size_fmt}[/red]")
        row.append(f"[red]{s.old.series_size_greedy_fmt}[/red]")
    summary.add_row(*row)

    # Never watched
    row = ["[bold]Never watched[/bold]"]
    if mode in ("all", "movies"):
        row.append(f"[purple]{s.never_watched.movie_count}[/purple]")
    if mode in ("all", "series"):
        row.append(f"[purple]{s.never_watched.shows_count}[/purple]")
        row.append("")
    if mode in ("all", "movies"):
        row.append(f"[purple]{s.never_watched.movie_size_fmt}[/purple]")
    if mode in ("all", "series"):
        row.append(f"[purple]{s.never_watched.series_size_fmt}[/purple]")
        row.append(f"[purple]{s.never_watched.series_size_greedy_fmt}[/purple]")
    summary.add_row(*row)

    # New (unwatched)
    row = ["[bold]New (unwatched)[/bold]"]
    if mode in ("all", "movies"):
        row.append(f"[cyan]{s.never_new.movie_count}[/cyan]")
    if mode in ("all", "series"):
        row.append(f"[cyan]{s.never_new.shows_count}[/cyan]")
        row.append("")
    if mode in ("all", "movies"):
        row.append(f"[cyan]{s.never_new.movie_size_fmt}[/cyan]")
    if mode in ("all", "series"):
        row.append(f"[cyan]{s.never_new.series_size_fmt}[/cyan]")
        row.append(f"[cyan]{s.never_new.series_size_greedy_fmt}[/cyan]")
    summary.add_row(*row)

    # Library
    summary.add_section()
    row = ["Library total"]
    if mode in ("all", "movies"):
        row.append(str(s.library.movie_count))
    if mode in ("all", "series"):
        row.append(str(s.library.shows_count))
        row.append("")
    if mode in ("all", "movies"):
        row.append(f"[dim]{s.library.movie_size_fmt}[/dim]")
    if mode in ("all", "series"):
        row.append(f"[dim]{s.library.series_size_fmt}[/dim]")
        row.append(f"[dim]{s.library.series_size_greedy_fmt}[/dim]")
    summary.add_row(*row)

    row = ["Kept"]
    if mode in ("all", "movies"):
        row.append(f"[yellow]{s.kept.movie_count}[/yellow]")
    if mode in ("all", "series"):
        row.append(f"[yellow]{s.kept.shows_count}[/yellow]")
        row.append(f"[yellow]{s.kept.seasons_count}[/yellow]")
    if mode in ("all", "movies"):
        row.append(f"[yellow]{s.kept.movie_size_fmt}[/yellow]")
    if mode in ("all", "series"):
        row.append(f"[yellow]{s.kept.series_size_fmt}[/yellow]")
        row.append(f"[yellow]{s.kept.series_size_greedy_fmt}[/yellow]")
    summary.add_row(*row)

    # Matching
    summary.add_section()
    row = ["Matched"]
    if mode in ("all", "movies"):
        row.append(f"[green]{s.matching.matched_movie_count}[/green]")
    if mode in ("all", "series"):
        row.append(f"[green]{s.matching.matched_shows_count}[/green]")
        row.append(f"[green]{s.matching.matched_seasons_count}[/green]")
    if mode in ("all", "movies"):
        row.append("")
    if mode in ("all", "series"):
        row.append("")
        row.append("")
    summary.add_row(*row)

    row = ["Ambiguous"]
    if mode in ("all", "movies"):
        row.append(f"[yellow]{s.matching.ambiguous_movie_count}[/yellow]")
    if mode in ("all", "series"):
        row.append(f"[yellow]{s.matching.ambiguous_shows_count}[/yellow]")
        row.append(f"[yellow]{s.matching.ambiguous_seasons_count}[/yellow]")
    if mode in ("all", "movies"):
        row.append("")
    if mode in ("all", "series"):
        row.append("")
        row.append("")
    summary.add_row(*row)

    row = ["Collision"]
    if mode in ("all", "movies"):
        row.append(f"[magenta]{s.matching.collision_movie_count}[/magenta]")
    if mode in ("all", "series"):
        row.append("")
        row.append(f"[magenta]{s.matching.collision_season_count}[/magenta]")
    if mode in ("all", "movies"):
        row.append("")
    if mode in ("all", "series"):
        row.append("")
        row.append("")
    summary.add_row(*row)

    row = ["Unmatched"]
    if mode in ("all", "movies"):
        row.append(f"[red]{s.matching.unmatched_movie_count}[/red]")
    if mode in ("all", "series"):
        row.append(f"[red]{s.matching.unmatched_shows_count}[/red]")
        row.append(f"[red]{s.matching.unmatched_seasons_count}[/red]")
    if mode in ("all", "movies"):
        row.append("")
    if mode in ("all", "series"):
        row.append("")
        row.append("")
    summary.add_row(*row)

    # Episode resolution stats
    if mode in ("all", "series"):
        if s.episodes.unparseable or s.episodes.skipped:
            summary.add_section()
        if s.episodes.unparseable:
            row = ["Episodes unparseable (no season number)"]
            if mode == "all":
                row.append("")
            row += ["", f"[yellow]{s.episodes.unparseable}[/yellow]"]
            if mode in ("all", "movies"):
                row.append("")
            if mode in ("all", "series"):
                row.append("")
                row.append("")
            summary.add_row(*row)
        if s.episodes.skipped:
            row = ["Episodes skipped (no data)"]
            if mode == "all":
                row.append("")
            row += ["", f"[dim]{s.episodes.skipped}[/dim]"]
            if mode in ("all", "movies"):
                row.append("")
            if mode in ("all", "series"):
                row.append("")
                row.append("")
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
        collision_movie_matches=result.collision_movie_matches,
        collision_season_matches=result.collision_season_matches,
        month_threshold=month_threshold,
    )

    console.print(Panel(
        f"[bold green]Report written to:[/bold green] [cyan]{output_path}[/cyan]",
        border_style="green",
    ))


if __name__ == '__main__':
    run()
