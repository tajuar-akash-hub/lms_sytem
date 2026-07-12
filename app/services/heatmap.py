from datetime import date

from app.schemas import HeatmapResult

# Weights for GitHub-style contribution scoring.
MODULE_WATCH_WEIGHT = 10
QUIZ_PASS_WEIGHT = 8
ASSIGNMENT_WEIGHT = 12
REVISION_MINUTE_WEIGHT = 1

# Score thresholds mapped to heatmap colors (0-100 scale).
MAX_DAILY_CONTRIBUTION = 100


def calculate_contribution_score(
    modules_watched: int,
    quizzes_passed: int,
    assignments_submitted: int,
    revision_minutes: int,
) -> int:
    """Sum weighted daily activities into a single contribution score."""
    return (
        modules_watched * MODULE_WATCH_WEIGHT
        + quizzes_passed * QUIZ_PASS_WEIGHT
        + assignments_submitted * ASSIGNMENT_WEIGHT
        + revision_minutes * REVISION_MINUTE_WEIGHT
    )


def heatmap_color(contribution_score: int) -> str:
    percentage = min(contribution_score / MAX_DAILY_CONTRIBUTION, 1.0) * 100
    if percentage <= 20:
        return "cry"
    if percentage <= 49:
        return "yellow"
    if percentage <= 89:
        return "light_green"
    return "dark_green"


def calculate_heatmap_from_activity(
    modules_watched: int = 0,
    quizzes_passed: int = 0,
    assignments_submitted: int = 0,
    revision_minutes: int = 0,
    activity_date: date | None = None,
) -> HeatmapResult:
    """
    GitHub-style heatmap based on daily contribution score.
    Streak maintenance still uses separate streak logic in streak.py.
    """
    del activity_date  # reserved for future day-specific weighting

    contribution_score = calculate_contribution_score(
        modules_watched=modules_watched,
        quizzes_passed=quizzes_passed,
        assignments_submitted=assignments_submitted,
        revision_minutes=revision_minutes,
    )
    percentage = round(
        min(contribution_score / MAX_DAILY_CONTRIBUTION, 1.0) * 100,
        2,
    )
    requirements_met = contribution_score > 0

    return HeatmapResult(
        percentage=percentage,
        color=heatmap_color(contribution_score),
        requirements_met=requirements_met,
    )
