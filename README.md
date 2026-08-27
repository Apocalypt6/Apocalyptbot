# Apocalyptbot

A Polymarket CLOB hunter. Version 0.2.

It is not a crypto candle bot. It does not watch BTC-USD bars, compute RSI,
or pretend a moving-average crossover is an edge. It reads Polymarket's public
APIs, scores books, and (if you ask) paper-trades the scores.

Nothing here is financial advice. Completeness arb is a thin, fragile
mechanical edge. Endgame, whale-copy, and momentum can lose the whole
bankroll. Never trade money you cannot afford to lose.

## What it does

- **scan** — hottest markets by 24h volume (Gamma).
- **hunt** — completeness (buy YES+NO asks under $1 after fees), merge (sell
  both bids over $1), wide spreads, late-game extremes, whale tape.
- **tape** — large prints from the Data API.
- **whale ADDRESS** — that wallet's positions and recent trades.
- **market SLUG** — one market, both books, recent tape, hunt scores.
- **paper** — simulated money against live books. Default strategy:
  `completeness`.
- **live** — real CLOB V2 orders. Refused unless you pass
  `--i-understand-this-risks-real-money` **and** set `POLYMARKET_PRIVATE_KEY`.
  Needs the optional `py-clob-client-v2` extra. The archived `py-clob-client`
  will not work.
- **health** — heartbeat freshness (Docker / systemd probes).
- **research** — disabled. Paid web search is not on the hunt path.

Hunt uses three **free, unauthenticated** hosts:

| Host | Role |
|------|------|
| `https://gamma-api.polymarket.com` | events, markets, slugs |
| `https://clob.polymarket.com` | order books |
| `https://data-api.polymarket.com` | trades, positions, holders |

No Polymarket API key is required for scan, hunt, tape, whale, market, paper,
or health. Do not paste an Exa (or any paid search) key into `.env` thinking
the bot needs it. It does not. Instant search is about **$7 per 1,000
queries**. This repo will not spend your $16 free-tier balance.

## What it does not do

It does not print money. Completeness is the only setup with a mechanical
payout identity (YES + NO = $1 at resolution). It still dies to **taker
fees**, **latency**, and **size that is gone by the time you send**. Merge
needs inventory you already hold. Wide books, endgame favorites, and copying
whales are opinions with extra logging.

CLOB books are **not reliably sorted**. The bot uses `max(bid)` / `min(ask)`
and sorts locally before walking depth. If you take the first row of a raw
`/book` payload as "best", you will misread the market.

Collateral on live orders is **pUSD** on **Polygon, chain id 137**.

## Quick start (venv)

Requires Python 3.9+.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
```

Same CLI either way:

```bash
python -m apocalyptbot scan
python beast.py hunt --limit 20
```

If the package is installed, `apocalyptbot` is also on `PATH`.

Dev extras (pytest) and the live CLOB client:

```bash
pip install -e ".[dev]"
pip install -e ".[live]"           # py-clob-client-v2 only; not required for paper
```

Or: `pip install -r requirements.txt` (requests + pytest, no live client).

## Commands

```bash
python -m apocalyptbot scan --limit 20
python -m apocalyptbot hunt --limit 40
python -m apocalyptbot hunt --watch --poll 30 --limit 40
python -m apocalyptbot tape --min-usd 2500
python -m apocalyptbot whale 0xYourProxyWallet
python -m apocalyptbot market will-the-fed-cut-rates-in-september-2026
python -m apocalyptbot paper --strategy completeness --cash 1000 --once
python -m apocalyptbot paper --strategy completeness --poll 30 --state state/portfolio.state.json
python -m apocalyptbot live --i-understand-this-risks-real-money   # real money
python -m apocalyptbot health --heartbeat state/heartbeat --max-age 900
python -m apocalyptbot research "some query"                       # exits refused
```

Useful flags (see `--help` on each subcommand):

| Flag | Used by | Default | Meaning |
|------|---------|---------|---------|
| `--limit` | scan, hunt, paper | 40 | hot markets to pull |
| `--min-edge` | hunt, paper | 0.008 | $0.008 / share after fees |
| `--min-shares` | hunt, paper | 20 | ignore thinner books |
| `--kinds` | hunt | all | `completeness,merge,wide_spread,endgame,whale` |
| `--watch` / `--poll` | hunt | off / 30s | loop |
| `--strategy` | paper, live | `completeness` | see [Strategies](#strategies) |
| `--param key=value` | paper, live | — | strategy kwargs (`limit=2`) |
| `--cash` | paper, live | 1000 | starting paper cash (pUSD) |
| `--max-notional` | paper, live | 50 | per-trade notional cap |
| `--max-exposure` | paper, live | 500 | inventory cap |
| `--max-daily-loss` | paper, live | 75 | halt buys after a bad day |
| `--json` | most read cmds | off | machine-readable |

## Sample output

`python -m apocalyptbot scan --limit 6` (illustrative numbers):

```
 #  MARKET                                                YES    NO   SPRD  VOL24H     LIQ
--  ----------------------------------------------------  -----  -----  ----  ------  ------
 1  Will the Fed cut rates at the September 2026 FOMC?    0.622  0.381  0.012   $890k   $188k
 2  Will Bitcoin close above $100k on August 31?          0.410  0.595  0.018   $412k    $96k
 3  Next US presidential election winner: Democratic nom  0.335  0.670  0.021   $301k   $240k
 4  Will there be a Ukraine ceasefire by August 31?       0.941  0.062  0.014   $188k    $41k
 5  Best Picture winner: The Brutalist                    0.210  0.790  0.061    $74k    $19k
 6  ETH above $5,000 by December 31, 2026?                0.448  0.560  0.009    $61k    $33k
6 markets  ·  free Gamma + CLOB reads
```

`python -m apocalyptbot hunt --limit 40` (illustrative):

```
hunted 40 books  ·  5 prints
#  KIND           MARKET                                      EDGE    SH      $
-  -------------  ------------------------------------------  ------  --  -----
1  completeness   Will the Fed cut rates at the September FO  0.82¢   84    $83
2  merge          Will Bitcoin close above $100k on August    1.18¢   31    $31
3  endgame        Will there be a Ukraine ceasefire by Augu  44.10¢    5     $5
4  whale          ETH above $5,000 by December 31, 2026?     52.80¢ 12000 $5,280
5  wide_spread    Best Picture winner: The Brutalist          6.10¢   50    $14

  1. buy Yes@0.4810 + No@0.5090 = 0.9900  →  $1.00  edge 0.82¢/sh  fees $0.0412
  2. sell Yes@0.6120 + No@0.4010 = 1.0130  vs $1.00  edge 1.18¢/sh (needs inventory)
  3. Yes mid 0.941  11.4h left  favorite — this is NOT free money
  4. 0x4f2a1c… BUY 12000 Yes @ 0.440  ($5,280)
  5. The Brutalist spread 0.061  bid 0.210 / ask 0.271
```

A 0.82¢ completeness print after fees is small. Walk away from any README
(this one included) that treats that as a business.

## Completeness, merge, and the rest

**Completeness** — buy YES and NO at the ask so that
`avg(YES) + avg(NO) + taker fees < $1`. At resolution one side pays $1, the
other $0. That is the identity. The bot walks both ask ladders in lockstep
and stops when average edge falls below `--min-edge`.

**Merge** — the other direction: sell both bids so
`avg(YES) + avg(NO) - fees > $1`. You must already hold the shares. The risk
gate will refuse a naked merge.

**Wide spread** — a book with a large bid/ask gap. Fade is an opinion that
someone will fill the hole. Often nobody does.

**Endgame** — a market near its `endDate` trading at an extreme price. Black
swans live here. A 94¢ favorite with eleven hours left is not "free 6 cents."

**Whale tape** — a large Data API print, surfaced so you can look. Copying it
is `copy_whale` / `momentum`. Whales are wrong constantly.

Paper and live run the same hunt, then a **strategy** picks among the already
ranked rows, then a **risk gate** clips size and can refuse the trade.

## Fees

Official taker curve (2026):

```
fee = shares * fee_rate * p * (1 - p)
```

Makers are not charged. Geopolitics is fee-free. Gamma's `takerBaseFee`
integer is not the rate — the bot maps `feeType` to the published category
rates:

| Category | Rate |
|----------|------|
| crypto | 0.07 |
| sports | 0.05 |
| finance, politics, tech, mentions | 0.04 |
| economics, culture, weather | 0.05 |
| geopolitics | 0.00 |

Fees peak around 50¢ outcomes. A "1¢ completeness" on a 50/50 crypto market
is often negative after the curve. The hunter subtracts fees before it
reports edge. It cannot subtract the fill you did not get.

## Strategies

| Name | What it takes | Honest note |
|------|----------------|-------------|
| `completeness` | `completeness` and `merge` rows | Only mechanical pair trades |
| `fade` | `wide_spread` | Spread is not a forecast |
| `endgame` | `endgame` | Can go to zero |
| `copy_whale` | `whale` | Large ≠ right |
| `momentum` | `whale` and `endgame` | Gambling with extra steps |

```bash
python -m apocalyptbot paper --strategy completeness --param limit=2 --once
```

## Paper vs live

**Paper** marks fills at the quoted prices, charges the taker curve, and
writes `state/portfolio.state.json`. There are no partials, no latency, and
no disappearing size. Treat the equity line as a filter for bad ideas, not a
promise the CLOB will still be there.

**Live** posts GTC orders through `py-clob-client-v2` on CLOB V2 (live as of
2026). The old `py-clob-client` package is archived and will not work.

```bash
export POLYMARKET_PRIVATE_KEY=0x...
export POLYMARKET_FUNDER=0x...          # optional; signature type 0 if you sign yourself
export POLYMARKET_SIGNATURE_TYPE=0
python -m apocalyptbot live \
    --i-understand-this-risks-real-money \
    --strategy completeness \
    --cash 100 \
    --max-notional 20 \
    --once
```

Without the flag or the key, `live` exits 2 and places nothing.
`deploy/run.sh` and the systemd unit **refuse** `MODE=live`. Unattended
deploys are hunt or paper only.

## Research is off

`python -m apocalyptbot research "..."` is a stub. It will not call Exa or
any other paid search API, even if `EXA_API_KEY` is set. Hunt does not "enrich"
markets with web search. Leave the key blank. If you later want paid search,
that is a separate, budgeted decision — not something to hang off `--watch`.

## Configuration

Copy [`.env.example`](.env.example) to `.env`. `deploy/run.sh` (Docker and
systemd) turns those variables into a `hunt` or `paper` argv. Changing
`MIN_EDGE` in `.env` only affects the unattended entrypoint; a manual
`python -m apocalyptbot hunt` still needs `--min-edge` if you want a
non-default threshold.

Optional Telegram (`APOCALYPTBOT_TELEGRAM_TOKEN` + `_CHAT_ID`) or a Discord /
Slack incoming webhook (`APOCALYPTBOT_WEBHOOK_URL`) fire on paper/live fills
and engine errors. If they are empty, notifications are skipped.

## Run it unattended

Paper is only useful if it stays up. The kit in [`deploy/`](deploy/README.md):

- `deploy/bootstrap.sh` — light VPS setup (updates, SSH-only firewall,
  fail2ban, chrony, venv, systemd). Hunt or paper. Not live.
- `Dockerfile` + `docker-compose.yml` — non-root `apocalypt` user, 1 GB cap,
  `restart: unless-stopped`, heartbeat `HEALTHCHECK`.
- `python -m apocalyptbot health` — stale `state/heartbeat` fails the probe.

```bash
cp .env.example .env          # MODE=paper for a simulated loop
docker compose up -d --build
```

Or, on a VPS: `sudo ./deploy/bootstrap.sh`, edit `.env`, `systemctl start apocalyptbot`.

## Project layout

```
apocalyptbot/
  cli.py           python -m apocalyptbot / beast.py
  gamma.py         Gamma discovery (no auth)
  clob.py          CLOB books (no auth)
  tape.py          Data API prints / positions
  hunt.py          rank completeness, merge, spreads, endgame, whales
  books.py         walk both sides; completeness / merge math
  fees.py          taker curve + category rates
  models.py        Market, Book, Opportunity, Print
  engine.py        hunt → strategy → risk → broker → state
  broker.py        PaperBroker; LiveBroker (opt-in CLOB V2)
  risk.py          notional / exposure / daily-loss gates
  portfolio.py     cash + outcome-token inventory (pUSD)
  research.py      paid search stub — always refused
  strategies/      completeness, fade, endgame, copy_whale, momentum
beast.py           thin launcher
deploy/            VPS + Docker entrypoints
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Disclaimer

This software is for education and research. It is not financial advice,
not an offer to trade, and not a claim that any strategy has a positive
expectation. Prediction-market trading can wipe a bankroll in a single
resolution. You are solely responsible for any use of this code and any
money you choose to put at risk. Never trade money you cannot afford to lose.
