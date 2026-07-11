# Hyperliquid Public Adapter V1

Read-only public market data integration for Hyperliquid perpetuals (BTC, ETH, SOL).

## Endpoints

| Network | HTTP | WebSocket |
|---------|------|-----------|
| Mainnet | `https://api.hyperliquid.xyz` | `wss://api.hyperliquid.xyz/ws` |
| Testnet | `https://api.hyperliquid-testnet.xyz` | `wss://api.hyperliquid-testnet.xyz/ws` |

Configured via `HyperliquidPublicConfig` — no hardcoded URLs in domain logic.

## HTTP Flows

### Meta validation

```
POST /info
{"type": "meta"}
```

Universe must contain BTC, ETH, SOL as perpetual symbols. Unknown or missing symbols fail-closed.

### Historical candles

```
POST /info
{
  "type": "candleSnapshot",
  "req": {
    "coin": "BTC",
    "interval": "1d",
    "startTime": <epoch_ms>,
    "endTime": <epoch_ms>
  }
}
```

Interval mapping: `1D→1d`, `1W→1w`, `1M→1M`.

Pagination: ascending output, no cross-page duplicates, stops on empty page / endTime / stagnant timestamp. Max ~5000 candles per response; multi-page with configurable page limit.

## Candle Schema

| Field | Meaning |
|-------|---------|
| t | Open time (epoch ms) |
| T | Close time (epoch ms) |
| s | Symbol |
| i | Interval |
| o,h,l,c | OHLC (Decimal-parsed) |
| v | Volume in base unit |
| n | Trade count |

No reliable `closed` field — closure derived from `T <= evaluation_time` in domain kernel.

## WebSocket

Subscribe (9 streams: 3 symbols × 3 timeframes):

```json
{"method":"subscribe","subscription":{"type":"candle","coin":"BTC","interval":"1d"}}
```

Ack: `channel=subscriptionResponse`. CONNECTED only after all required acks.

Live candles: `channel=candle`. Open candle updates allowed; closed candle conflicts detected.

Heartbeat: `{"method":"ping"}` → `{"channel":"pong"}`.

## Reconnect (race-free)

1. Connect WS
2. Subscribe + confirm acks
3. Buffer incoming events
4. HTTP backfill per symbol/timeframe
5. Ingest backfill via shared `ingest_raw_batch`
6. Replay buffer via `ingest_live_raw`
7. Resume live processing

Buffer overflow → fail-closed reconnect.

## Runtime

`HyperliquidMarketDataRuntime`:

- `backfill_symbol(...)` — meta check, HTTP fetch, shared ingest, gap detection
- `start(evaluation_time)` — meta, WS connect, initial backfill, buffer replay
- `process_live(evaluation_time)` — drain WS queue through live ingest
- `reconnect(evaluation_time)` — WS reconnect + HTTP backfill + buffer replay
- `status(evaluation_time)` — readiness, subscriptions, series quality

Readiness requires: meta OK, all subscriptions acked, initial backfill done, no unresolved conflicts, required series not INVALID/DISCONNECTED.

## Rate Limits

- HTTP concurrency limiter (default 2)
- Retries: timeout, connection, 429, 5xx with exponential backoff
- No retry: 4xx, parse errors, unknown symbols
- Single WebSocket connection for all subscriptions

## Live Smoke Tests

Enabled only when **both** environment variables are set:

```bash
RUN_HYPERLIQUID_LIVE_TESTS=1
HYPERLIQUID_NETWORK=testnet
```

```bash
python -m pytest tests/market_data/hyperliquid -m live -v -s
```

| Test | Endpoint | Checks |
|------|----------|--------|
| `test_live_testnet_fetches_perpetual_meta` | `POST /info` `type=meta` | Universe contains BTC/ETH/SOL |
| `test_live_testnet_fetches_small_daily_candle_snapshot` | `POST /info` `candleSnapshot` | BTC 1d closed candles, OHLC/volume/timestamps |
| `test_live_testnet_websocket_subscription_ack` | `wss://…/ws` subscribe BTC/1d | Single subscription ack |
| `test_live_testnet_ping_pong` | `wss://…/ws` ping | `channel=pong` response |

Guard tests (`test_live_guard_*`) run in the standard suite and verify skip behaviour without network access.

Standard pytest never uses real network unless both env vars are set.

## Known Limits

- Hyperliquid returns at most ~5000 recent candles per snapshot request
- Monthly interval uses `1M` (case-sensitive)
- Volume is base-unit, not quote-unit
- No wallet, signing, orders, or user endpoints

## Dependencies

- `httpx` — async HTTP
- `websockets` — WebSocket client
