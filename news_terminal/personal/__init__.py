"""Personal intelligence module — scores articles against your profile."""

from news_terminal.personal.scorer import PersonalScorer
from news_terminal.personal.brief import generate_decision_brief
from news_terminal.personal.tracker import PredictionTracker

__all__ = ["PersonalScorer", "generate_decision_brief", "PredictionTracker"]
