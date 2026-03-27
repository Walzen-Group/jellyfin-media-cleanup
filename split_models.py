import ast
import os
import sys

def get_ast_node_source(source, node):
    lines = source.split('\n')
    return '\n'.join(lines[node.lineno-1:node.end_lineno])

def main():
    with open('src/media_cleanup/_models_old.py', 'r', encoding='utf-8') as f:
        source = f.read()
    
    tree = ast.parse(source)
    nodes = {node.name: node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))}

    def get_source(names):
        out = []
        for name in names:
            if name in nodes:
                out.append(get_ast_node_source(source, nodes[name]))
        return '\n\n\n'.join(out)

    base_names = ['_Base', 'JobStatus', '_unique_shows', '_movie_size', '_season_size', '_format_size', '_never_status']
    jobs_names = ['JobResponse', 'ProgressMessage']
    summary_names = ['CategoryStats', 'MatchingStats', 'EpisodeStats', 'SpaceSavings', 'SummaryModel', '_make_category', 'build_summary']
    analysis_names = ['AnalysisRequest', 'MovieMatch', 'SeasonInfo', 'SeriesGroup', 'MediaSection', 'AnalysisResult', '_title_from_path', 'match_result_to_model', '_derive_show_status', '_build_all_series_groups', '_movie_to_match', 'cleanup_result_to_response']
    filter_names = ['FilterRequest', 'FilteredSummary', 'FilteredResult', 'filter_analysis_result']
    run_plan_names = ['MovieDeletion', 'FullSeriesDeletion', 'SeasonCleanup', 'RunPlanSummary', 'RunPlan', 'build_run_plan']
    cleanup_names = ['CleanupLogEntry', 'CleanupReport', 'HistoryEntry', 'CleanupExecuteRequest', 'CleanupJobResponse']

    os.makedirs('src/media_cleanup/models', exist_ok=True)
    
    def write_f(filename, imports, names):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(imports + '\n\n' + get_source(names) + '\n')

    # Base
    base_imports = '''"""
Base models and shared helper functions.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from media_cleanup.matching import MatchResult
from media_cleanup.types import MediaStatus, SeasonSummary
'''
    write_f('src/media_cleanup/models/base.py', base_imports, base_names)

    # Jobs
    jobs_imports = '''"""
Job models.
"""
from __future__ import annotations
from .base import _Base, JobStatus
'''
    write_f('src/media_cleanup/models/jobs.py', jobs_imports, jobs_names)

    # Summary
    summary_imports = '''"""
Summary statistics models and builder.
"""
from __future__ import annotations
from media_cleanup.schema.radarr_schema import Movie
from media_cleanup.schema.sonarr_schema import Series
from media_cleanup.service import CleanupResult
from media_cleanup.types import MediaStatus

from .base import _Base, _format_size, _movie_size, _never_status, _season_size, _unique_shows
'''
    write_f('src/media_cleanup/models/summary.py', summary_imports, summary_names)

    # Analysis
    analysis_imports = '''"""
Analysis models and builders.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any

from media_cleanup.matching import MatchResult
from media_cleanup.schema.radarr_schema import Movie
from media_cleanup.schema.sonarr_schema import Series
from media_cleanup.service import CleanupResult
from media_cleanup.types import MatchMethod, MediaMode, MediaStatus, SeasonSummary

from .base import _Base, _never_status
from .summary import SummaryModel, build_summary
'''
    write_f('src/media_cleanup/models/analysis.py', analysis_imports, analysis_names)

    # Filter
    filter_imports = '''"""
Filter models and result filtering.
"""
from __future__ import annotations
from typing import Sequence
from media_cleanup.types import FilterCategory, MediaMode, MediaStatus
from .base import _Base, _format_size
from .analysis import AnalysisResult, MediaSection, MovieMatch, SeriesGroup
'''
    write_f('src/media_cleanup/models/filter.py', filter_imports, filter_names)

    # Run Plan
    run_plan_imports = '''"""
Run plan models and generation.
"""
from __future__ import annotations
from typing import Sequence
from .base import _Base, _format_size
from .filter import FilteredResult
'''
    write_f('src/media_cleanup/models/run_plan.py', run_plan_imports, run_plan_names)

    # Cleanup
    cleanup_imports = '''"""
Cleanup execution models.
"""
from __future__ import annotations
from media_cleanup.types import CleanupEntryStatus, CleanupMediaType
from .base import _Base, JobStatus
from .run_plan import FullSeriesDeletion, MovieDeletion, SeasonCleanup
'''
    write_f('src/media_cleanup/models/cleanup.py', cleanup_imports, cleanup_names)

    # __init__.py
    init_content = '''"""
Package exports for models.
"""
from .base import JobStatus, _format_size
from .analysis import AnalysisRequest, AnalysisResult, MediaSection, MovieMatch, SeasonInfo, SeriesGroup, cleanup_result_to_response, match_result_to_model
from .cleanup import CleanupExecuteRequest, CleanupJobResponse, CleanupLogEntry, CleanupReport, HistoryEntry
from .filter import FilterRequest, FilteredResult, FilteredSummary, filter_analysis_result
from .jobs import JobResponse, ProgressMessage
from .run_plan import FullSeriesDeletion, MovieDeletion, RunPlan, RunPlanSummary, SeasonCleanup, build_run_plan
from .summary import CategoryStats, EpisodeStats, MatchingStats, SpaceSavings, SummaryModel, build_summary

__all__ = [
    "AnalysisRequest",
    "AnalysisResult",
    "CategoryStats",
    "CleanupExecuteRequest",
    "CleanupJobResponse",
    "CleanupLogEntry",
    "CleanupReport",
    "EpisodeStats",
    "FilterRequest",
    "FilteredResult",
    "FilteredSummary",
    "FullSeriesDeletion",
    "HistoryEntry",
    "JobResponse",
    "JobStatus",
    "MatchingStats",
    "MediaSection",
    "MovieDeletion",
    "MovieMatch",
    "ProgressMessage",
    "RunPlan",
    "RunPlanSummary",
    "SeasonCleanup",
    "SeasonInfo",
    "SeriesGroup",
    "SpaceSavings",
    "SummaryModel",
    "_format_size",
    "build_run_plan",
    "build_summary",
    "cleanup_result_to_response",
    "filter_analysis_result",
    "match_result_to_model",
]
'''
    with open('src/media_cleanup/models/__init__.py', 'w', encoding='utf-8') as f:
        f.write(init_content)
        
    print("Done")

if __name__ == '__main__':
    main()
