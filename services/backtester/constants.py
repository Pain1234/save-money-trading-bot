"""Backtester constants."""

BACKTESTER_VERSION = "1.0.0"
DEFAULT_SYMBOLS = ("BTC", "ETH", "SOL")
EVALUATION_BUFFER_SECONDS = 5

# Intrabar assumption (documented in README): after entry fill at open,
# stop is checked on the same candle (conservative for long).
INTRABAR_ASSUMPTION = "ENTRY_AT_OPEN_THEN_STOP_SAME_CANDLE"
