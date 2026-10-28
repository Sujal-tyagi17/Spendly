"""Loads and compiles the rule registry in ``config/rules.json``.

Keeping every merchant alias and category rule in one config file means
new merchants can be added without touching Python code, and there are no
merchant-name ``if`` statements scattered through the codebase.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src import config


@dataclass(frozen=True)
class TypeRule:
    name: str
    pattern: re.Pattern
    transaction_type: str
    category: str
    direction: str | None = None
    merchant: str | None = None


@dataclass(frozen=True)
class MerchantRule:
    name: str
    patterns: tuple[re.Pattern, ...]
    category: str | None


@dataclass(frozen=True)
class RuleSet:
    type_rules: tuple[TypeRule, ...]
    merchants: tuple[MerchantRule, ...]
    noise_tokens: frozenset[str]
    bank_codes: frozenset[str]

    def merchant_category(self, merchant: str) -> str | None:
        for rule in self.merchants:
            if rule.name == merchant:
                return rule.category
        return None

    @property
    def known_merchants(self) -> set[str]:
        return {rule.name for rule in self.merchants}


class RulesConfigError(ValueError):
    pass


def _compile(pattern: str, where: str) -> re.Pattern:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise RulesConfigError(f"Invalid regex in {where}: {pattern!r} ({exc})") from exc


def parse_rules(data: dict) -> RuleSet:
    valid_categories = set(config.CATEGORIES)
    valid_types = set(config.TRANSACTION_TYPES)

    type_rules = []
    for raw in data.get("type_rules", []):
        if raw["category"] not in valid_categories:
            raise RulesConfigError(f"Unknown category {raw['category']!r} in type rule {raw['name']!r}")
        if raw["transaction_type"] not in valid_types:
            raise RulesConfigError(f"Unknown transaction type in rule {raw['name']!r}")
        type_rules.append(
            TypeRule(
                name=raw["name"],
                pattern=_compile(raw["pattern"], f"type rule {raw['name']}"),
                transaction_type=raw["transaction_type"],
                category=raw["category"],
                direction=raw.get("direction"),
                merchant=raw.get("merchant"),
            )
        )

    merchants = []
    for raw in data.get("merchants", []):
        category = raw.get("category")
        if category is not None and category not in valid_categories:
            raise RulesConfigError(f"Unknown category {category!r} for merchant {raw['name']!r}")
        merchants.append(
            MerchantRule(
                name=raw["name"],
                patterns=tuple(_compile(p, f"merchant {raw['name']}") for p in raw["patterns"]),
                category=category,
            )
        )

    return RuleSet(
        type_rules=tuple(type_rules),
        merchants=tuple(merchants),
        noise_tokens=frozenset(t.upper() for t in data.get("noise_tokens", [])),
        bank_codes=frozenset(t.upper() for t in data.get("bank_codes", [])),
    )


@lru_cache(maxsize=4)
def load_rules(path: str | None = None) -> RuleSet:
    rules_path = Path(path) if path else config.RULES_PATH
    with open(rules_path, encoding="utf-8") as handle:
        return parse_rules(json.load(handle))
