"""Central configuration for Spendly.

Everything that a user might reasonably want to tune lives here, and every
value can be overridden with an environment variable so that nothing is
hardcoded to one machine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("SPENDLY_DATA_DIR", PROJECT_ROOT / "data"))
SQL_DIR = PROJECT_ROOT / "sql"
RULES_PATH = Path(os.getenv("SPENDLY_RULES_PATH", PROJECT_ROOT / "config" / "rules.json"))
SAMPLE_CSV_PATH = PROJECT_ROOT / "data" / "sample_transactions.csv"

APP_NAME = "Spendly"
TAGLINE = "Every rupee tells a story."


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class UploadSettings:
    max_file_size_mb: int = _env_int("SPENDLY_MAX_UPLOAD_MB", 10)
    max_pages: int = _env_int("SPENDLY_MAX_PDF_PAGES", 60)

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@dataclass(frozen=True)
class RecurringSettings:
    min_occurrences: int = 3
    # Allowed drift (in days) around each billing period.
    interval_tolerance_days: dict = field(
        default_factory=lambda: {"weekly": 2, "monthly": 5, "quarterly": 10, "yearly": 15}
    )
    period_days: dict = field(
        default_factory=lambda: {"weekly": 7, "monthly": 30, "quarterly": 91, "yearly": 365}
    )
    # Max relative deviation from the median amount.
    high_confidence_amount_tolerance: float = 0.10
    possible_amount_tolerance: float = 0.30
    # Share of intervals that must fit the schedule.
    high_confidence_interval_share: float = 1.0
    possible_interval_share: float = 0.6


@dataclass(frozen=True)
class AnomalySettings:
    min_observations: int = 8
    iqr_multiplier: float = 1.5
    # A flagged amount must also be at least this many times the median, so
    # that tiny categories with very tight spreads don't flag ₹20 differences.
    min_ratio_to_median: float = 2.0
    merchant_min_observations: int = 5


@dataclass(frozen=True)
class AISettings:
    enabled_flag: bool = _env_bool("SPENDLY_ENABLE_AI", False)
    api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    timeout_seconds: int = _env_int("GEMINI_TIMEOUT_SECONDS", 20)
    max_merchants_per_request: int = 40

    @property
    def enabled(self) -> bool:
        """AI is used only when explicitly switched on AND a key exists."""
        return bool(self.enabled_flag and self.api_key)


# On a shared/public host (e.g. Streamlit Community Cloud) set
# SPENDLY_PUBLIC_DEPLOYMENT=true: every visitor then gets private, in-memory
# databases that vanish with their session, so nobody can see anyone else's data.
PUBLIC_DEPLOYMENT = _env_bool("SPENDLY_PUBLIC_DEPLOYMENT", False)

@dataclass(frozen=True)
class BudgetSettings:
    """Thresholds for budget statuses and insights. These are display conventions,
    not financial advice — change them to suit yourself."""
    near_threshold_pct: float = float(os.getenv("SPENDLY_BUDGET_NEAR_PCT", 80))
    pace_min_days: int = _env_int("SPENDLY_BUDGET_PACE_MIN_DAYS", 7)
    pace_tolerance_pct: float = 10.0       # within ±10% of the even pace counts as "on pace"
    repeat_window_months: int = 3          # look back this many months (incl. the selected one)
    repeat_min_months: int = 2             # over budget in at least this many of them
    max_amount_paise: int = 10_00_00_000_00  # ₹10 crore — a sanity limit, not a rule


UPLOAD = UploadSettings()
BUDGET = BudgetSettings()
RECURRING = RecurringSettings()
ANOMALY = AnomalySettings()


def ai_settings() -> AISettings:
    """Read AI settings at call time so tests / env changes are respected."""
    return AISettings(
        enabled_flag=_env_bool("SPENDLY_ENABLE_AI", False),
        api_key=os.getenv("GEMINI_API_KEY") or None,
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        timeout_seconds=_env_int("GEMINI_TIMEOUT_SECONDS", 20),
    )


def db_path(mode: str) -> Path:
    """Demo data and user data live in *separate* SQLite files so they can
    never be mixed by accident."""
    if mode not in {"demo", "user"}:
        raise ValueError(f"Unknown data mode: {mode!r}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"spendly_{mode}.db"


CATEGORIES = [
    "Food & Dining",
    "Groceries",
    "Transport",
    "Shopping",
    "Bills & Utilities",
    "Entertainment",
    "Healthcare",
    "Education",
    "Travel",
    "Subscriptions",
    "Rent & Housing",
    "Income",
    "Transfers",
    "Refunds",
    "Other",
]

UNCATEGORIZED = "Other"

# Categories that can hold a spending budget (money-in and movement categories can't).
BUDGET_CATEGORIES = [c for c in CATEGORIES if c not in {"Income", "Transfers", "Refunds"}]

TRANSACTION_TYPES = {
    "expense": "Expense",
    "income": "Income",
    "refund": "Refund",
    "transfer": "Internal transfer",
    "cc_repayment": "Credit card repayment",
    "other": "Other / unknown",
}
