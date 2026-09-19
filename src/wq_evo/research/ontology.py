from __future__ import annotations

from typing import Any


# Conservative, explainable mappings. These are research tags, not claims that a
# field is a validated alpha source. The live field metadata remains authoritative.
_KEYWORD_TRAITS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sentiment", ("sentiment",)),
    ("afinn", ("sentiment", "text_nlp")),
    ("ownership", ("ownership", "institutional_positioning")),
    ("institution", ("ownership", "institutional_positioning")),
    ("insider", ("insider_activity",)),
    ("short_volume", ("short_interest",)),
    ("short_interest", ("short_interest",)),
    ("estimate", ("analyst_expectations",)),
    ("forecast", ("analyst_expectations",)),
    ("consensus", ("analyst_expectations",)),
    ("recommendation", ("analyst_expectations",)),
    ("eps", ("earnings",)),
    ("earnings", ("earnings",)),
    ("revenue", ("fundamentals",)),
    ("sales", ("fundamentals",)),
    ("assets", ("fundamentals",)),
    ("equity", ("fundamentals",)),
    ("operating_income", ("fundamentals", "profitability")),
    ("ebit", ("fundamentals", "profitability")),
    ("margin", ("fundamentals", "profitability")),
    ("cash_flow", ("fundamentals", "cash_flow")),
    ("free_cash_flow", ("fundamentals", "cash_flow")),
    ("volume", ("price_volume", "liquidity")),
    ("adv", ("price_volume", "liquidity")),
    ("price", ("price_volume",)),
    ("close", ("price_volume",)),
    ("open", ("price_volume",)),
    ("high", ("price_volume",)),
    ("low", ("price_volume",)),
    ("volatility", ("risk",)),
    ("beta", ("risk",)),
    ("drawdown", ("risk",)),
    ("esg", ("alternative_data", "esg")),
)


def infer_field_traits(field: dict[str, Any]) -> set[str]:
    """Attach conservative semantic tags to a live field.

    The function only uses field metadata and name keywords. It is intentionally
    deterministic so the same catalog snapshot produces the same research map.
    """
    text = " ".join(
        str(field.get(k) or "")
        for k in ("id", "category", "dataset", "description", "name")
    ).lower()

    traits: set[str] = set()
    category = str(field.get("category") or "").lower()
    dataset = str(field.get("dataset") or "").lower()

    if "analyst" in category or "estimate" in dataset or "forecast" in dataset:
        traits.add("analyst_expectations")
    if "fundamental" in category:
        traits.add("fundamentals")
    if "price volume" in category:
        traits.add("price_volume")
    if "sentiment" in category:
        traits.add("sentiment")
    if "short interest" in category:
        traits.add("short_interest")
    if "institutions" in category:
        traits.add("institutional_positioning")
    if "news" in category:
        traits.add("news")
    if "social" in category:
        traits.add("social_media")
    if "risk" in category:
        traits.add("risk")

    for keyword, tags in _KEYWORD_TRAITS:
        if keyword in text:
            traits.update(tags)

    return traits
