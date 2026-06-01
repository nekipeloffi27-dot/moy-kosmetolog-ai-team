"""Token cost calculation. Update these if pricing changes."""

# USD per million tokens (input/output)
# These are 2026 prices for the Anthropic API — adjust if Anthropic raises.
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    # (input, output)
    "claude-opus-4-7":   (15.00, 75.00),
    "claude-opus-4-6":   (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5":  (1.00,  5.00),
}


def cost_cents(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> int:
    """Return cost in integer US cents (rounded up to avoid undercounting).

    cache_creation_tokens: written to cache, billed at 1.25× input price.
    cache_read_tokens: read from cache, billed at 0.1× input price.
    """
    if model not in PRICING_PER_MTOK:
        # Default to Opus rates to be safe
        in_price, out_price = PRICING_PER_MTOK["claude-opus-4-7"]
    else:
        in_price, out_price = PRICING_PER_MTOK[model]
    cost_usd = (
        input_tokens * in_price
        + output_tokens * out_price
        + cache_creation_tokens * in_price * 1.25
        + cache_read_tokens * in_price * 0.1
    ) / 1_000_000
    return int(round(cost_usd * 100))
