#!/usr/bin/env python3
"""Phase 1 orchestrator — static proof-of-concept pipeline.

Steps:
  1. Seed persons table
  2. Scrape Fed speech archive (2015–present)
  3. Run FinBERT offline on unscored statements
  4. Compute sentiment_signal (sharpe_analog) for all scored statements
  5. Fetch historical yfinance price data (US + EU + Asia indices, FX rates)
  6. Fetch FRED macro series (US + international series hosted on FRED)
  7. Fetch ECB Statistical Data Warehouse series (no API key required)
  8. Detect price events programmatically
  9. (Manual) open the notebook/dashboard to produce the scatter chart

Run from the project root with the venv active:
    python scripts/run_phase1.py [--steps 1,2,3]
"""

import argparse
import sys

sys.path.insert(0, ".")

from loguru import logger

from sentiment_signal.db.session import SessionLocal


def step1_seed_persons() -> None:
    logger.info("── Step 1: Seeding persons table ──")
    from scripts.seed_persons import main as seed

    seed()


def step2_scrape_fed(start_year: int = 2015) -> None:
    logger.info(f"── Step 2: Scraping Fed speeches from {start_year} ──")
    from sentiment_signal.collectors.fed_speeches import FedSpeechesScraper

    session = SessionLocal()
    try:
        scraper = FedSpeechesScraper(session, start_year=start_year)
        total = scraper.run()
        logger.info(f"Inserted {total} new statements")
    finally:
        session.close()


def step3_score_statements(batch_size: int = 100) -> None:
    logger.info("── Step 3: Scoring statements with FinBERT (chunked, full-document) ──")
    from sqlalchemy import select

    from sentiment_signal.db.models import Statement, StatementAnalysis
    from sentiment_signal.nlp.pipeline import FINBERT_CHUNKED_VERSION, NLPPipeline

    session = SessionLocal()
    try:
        # Score statements with no analysis, or whose analysis predates the current
        # scoring method (model_version mismatch) — e.g. rows scored before chunking,
        # which only saw each document's first 512 tokens.
        rows = (
            session.execute(
                select(Statement)
                .outerjoin(StatementAnalysis, StatementAnalysis.statement_id == Statement.id)
                .where(StatementAnalysis.model_version.is_distinct_from(FINBERT_CHUNKED_VERSION))
            )
            .scalars()
            .all()
        )
        logger.info(f"Statements needing (re)scoring: {len(rows)}")
        if not rows:
            return

        pipe = NLPPipeline()
        scored = 0
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            results = pipe.analyze_documents([s.raw_text for s in batch])
            existing = {
                a.statement_id: a
                for a in session.scalars(
                    select(StatementAnalysis).where(
                        StatementAnalysis.statement_id.in_([s.id for s in batch])
                    )
                ).all()
            }
            for stmt, res in zip(batch, results):
                analysis = existing.get(stmt.id)
                if analysis is None:
                    analysis = StatementAnalysis(statement_id=stmt.id)
                    session.add(analysis)
                analysis.sentiment_score = res["sentiment_score"]
                analysis.sentiment_label = res["sentiment_label"]
                analysis.embedding = res["embedding"]
                analysis.finbert_score = res["sentiment_score"]
                analysis.model_version = FINBERT_CHUNKED_VERSION
                stmt.is_processed = True
            session.commit()
            scored += len(batch)
            logger.info(f"step3: scored {scored}/{len(rows)}")
        logger.info(f"Scored {scored} statements (chunked, full-document)")
    finally:
        session.close()


def step4_compute_signals() -> None:
    logger.info("── Step 4: Computing sentiment_signal rows ──")
    from sqlalchemy import select

    from sentiment_signal.db.models import Statement
    from sentiment_signal.features.signal import build_signal_for_statement

    session = SessionLocal()
    try:
        processed = session.scalars(select(Statement).where(Statement.is_processed.is_(True))).all()
        built = 0
        for stmt in processed:
            sig = build_signal_for_statement(str(stmt.id), session)
            if sig:
                built += 1
        logger.info(f"Built {built} signal rows")
    finally:
        session.close()


def step5_fetch_prices() -> None:
    logger.info("── Step 5: Fetching yfinance historical prices ──")
    import yfinance as yf
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from sentiment_signal.db.models import PriceData

    SYMBOLS = [
        # US
        "^GSPC",
        "^VIX",
        "^IXIC",
        "^DJI",
        # Europe
        "^GDAXI",  # DAX (Germany)
        "^FTSE",  # FTSE 100 (UK)
        "^FCHI",  # CAC 40 (France)
        "^STOXX50E",  # Euro Stoxx 50
        # Asia-Pacific
        "^N225",  # Nikkei 225 (Japan)
        "^HSI",  # Hang Seng (Hong Kong)
        "000001.SS",  # Shanghai Composite (China)
        "^KS11",  # KOSPI (South Korea)
        "^AXJO",  # ASX 200 (Australia)
        # FX rates (quoted as USD per 1 unit of foreign currency)
        "EURUSD=X",
        "JPY=X",  # USD/JPY
        "GBPUSD=X",
        "CNY=X",  # USD/CNY
    ]
    session = SessionLocal()
    try:
        for symbol in SYMBOLS:
            logger.info(f"Downloading {symbol}")
            df = yf.Ticker(symbol).history(start="2015-01-01", auto_adjust=True)
            if df.empty:
                logger.warning(f"{symbol}: no data returned")
                continue
            rows = []
            for ts, row in df.iterrows():
                rows.append(
                    dict(
                        symbol=symbol,
                        granularity="1d",
                        timestamp=ts.to_pydatetime(),
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=int(row["Volume"]),
                    )
                )
            if rows:
                session.execute(
                    pg_insert(PriceData)
                    .values(rows)
                    .on_conflict_do_nothing(index_elements=["symbol", "granularity", "timestamp"])
                )
                session.commit()
                logger.info(f"{symbol}: {len(rows)} rows")
    finally:
        session.close()


def step6_fetch_macro() -> None:
    logger.info("── Step 6: Fetching FRED macro series ──")
    from sentiment_signal.config import settings

    if not settings.fred_api_key:
        logger.warning("FRED_API_KEY not set — skipping macro fetch")
        return

    import time

    from fredapi import Fred
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from sentiment_signal.db.models import MacroData

    SERIES = {
        # US monetary policy & macro
        "FEDFUNDS": "Federal Funds Rate",
        "CPIAUCSL": "CPI Urban Consumers",
        "UNRATE": "Unemployment Rate",
        "T10Y2Y": "10Y-2Y Yield Spread",
        "T10YIE": "10Y Breakeven Inflation",
        "VIXCLS": "VIX Close",
        "BAMLH0A0HYM2": "US HY Credit Spread",
        "DPCREDIT": "Fed Discount Rate",
        # Europe (hosted on FRED)
        "ECBDFR": "ECB Deposit Facility Rate (FRED mirror)",
        "IRLTLT01DEM156N": "Germany 10Y Bund Yield",
        "IRLTLT01GBM156N": "UK 10Y Gilt Yield",
        "IRLTLT01FRM156N": "France 10Y OAT Yield",
        "CP0000EZ19M086NEST": "Eurozone HICP Inflation",
        "LRHUTTTTEZM156S": "Eurozone Unemployment Rate",
        # Japan
        "IRLTLT01JPM156N": "Japan 10Y JGB Yield",
        "CPALTT01JPM659N": "Japan CPI YoY",
        "LRUNTTTTJPM156S": "Japan Unemployment Rate",
        # FX
        "EXJPUS": "JPY/USD Exchange Rate",
        "EXUSEU": "USD/EUR Exchange Rate",
        "EXCHUS": "CNY/USD Exchange Rate",
        "EXUSUK": "USD/GBP Exchange Rate",
        # Global
        "DEXBZUS": "BRL/USD Exchange Rate",
    }
    fred = Fred(api_key=settings.fred_api_key)
    session = SessionLocal()
    try:
        for series_id, description in SERIES.items():
            logger.info(f"FRED  {series_id}  {description}")
            try:
                data = fred.get_series(series_id, observation_start="2015-01-01")
            except Exception as exc:
                logger.warning(f"{series_id}: skipped — {exc}")
                time.sleep(2)
                continue
            time.sleep(0.5)
            rows = [
                {"series_id": series_id, "timestamp": ts.to_pydatetime(), "value": float(val)}
                for ts, val in data.dropna().items()
            ]
            if rows:
                session.execute(
                    pg_insert(MacroData)
                    .values(rows)
                    .on_conflict_do_nothing(index_elements=["series_id", "timestamp"])
                )
                session.commit()
                logger.info(f"{series_id}: {len(rows)} rows")
    finally:
        session.close()


def step7_fetch_ecb() -> None:
    logger.info("── Step 7: Fetching ECB Statistical Data Warehouse series ──")
    from sentiment_signal.collectors.ecb_sdw import run_ecb_fetch

    session = SessionLocal()
    try:
        run_ecb_fetch(session, start_period="2015-01")
    finally:
        session.close()


def step8_detect_events(threshold_mode: str = "pct", sigma: float = 2.0) -> None:
    """Detect daily price-move events across markets.

    threshold_mode 'pct' uses the fixed per-group percent threshold (default,
    unchanged); 'sigma' flags moves of |z| >= `sigma` standard deviations of that
    market's own daily returns, so event rarity is comparable across markets of
    different volatility. Either way, magnitude_z (the move in per-market return
    std) is stored on every event for volatility-normalised analysis.
    """
    logger.info(f"── Step 8: Detecting price events (multi-market, mode={threshold_mode}) ──")
    import pandas as pd
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from sentiment_signal.db.models import Event, PriceData

    # (symbol, market_group, threshold_pct)
    # FX moves less in percentage terms than equities so uses a tighter threshold.
    MARKET_CONFIG: list[tuple[str, str, float]] = [
        # US equity
        ("^GSPC", "equity_us", 1.0),
        ("^IXIC", "equity_us", 1.0),
        ("^DJI", "equity_us", 1.0),
        # European equity
        ("^GDAXI", "equity_eu", 1.0),
        ("^FTSE", "equity_eu", 1.0),
        ("^FCHI", "equity_eu", 1.0),
        ("^STOXX50E", "equity_eu", 1.0),
        # Asia-Pacific equity
        ("^N225", "equity_ap", 1.0),
        ("^HSI", "equity_ap", 1.0),
        ("000001.SS", "equity_ap", 1.0),
        ("^KS11", "equity_ap", 1.0),
        ("^AXJO", "equity_ap", 1.0),
        # Major FX pairs
        ("EURUSD=X", "fx_major", 0.5),
        ("JPY=X", "fx_major", 0.5),
        ("GBPUSD=X", "fx_major", 0.5),
        ("CNY=X", "fx_major", 0.5),
    ]

    session = SessionLocal()
    try:
        total_inserted = 0
        for symbol, market_group, threshold_pct in MARKET_CONFIG:
            rows = session.execute(
                select(PriceData.timestamp, PriceData.close)
                .where(PriceData.symbol == symbol, PriceData.granularity == "1d")
                .order_by(PriceData.timestamp)
            ).all()
            if not rows:
                logger.warning(f"{symbol}: no price data — run step 5 first")
                continue

            df = pd.DataFrame(rows, columns=["timestamp", "close"]).set_index("timestamp")
            df["close"] = df["close"].astype(
                float
            )  # close is NUMERIC -> Decimal; cast so .std() works
            df["pct_change"] = df["close"].pct_change() * 100
            market_std = float(df["pct_change"].std())  # volatility of this market's daily returns
            if not market_std or pd.isna(market_std):  # 0 or NaN -> cannot normalise
                market_std = 0.0

            events = []
            for ts, row in df.dropna().iterrows():
                pct = float(row["pct_change"])
                z = pct / market_std if market_std else None
                if threshold_mode == "sigma":
                    is_event = market_std > 0 and abs(z) >= sigma
                    cutoff = round(sigma * market_std, 4) if market_std else threshold_pct
                else:
                    is_event = abs(pct) >= threshold_pct
                    cutoff = threshold_pct
                if is_event:
                    events.append(
                        dict(
                            event_type="price_move",
                            domain=symbol,
                            timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                            window_hours=24,
                            magnitude_pct=round(pct, 4),
                            magnitude_z=round(z, 4) if z is not None else None,
                            direction=1 if pct > 0 else -1,
                            threshold_pct=cutoff,
                            is_scheduled=False,
                            source="programmatic",
                            notes=market_group,
                        )
                    )

            if events:
                session.execute(
                    pg_insert(Event)
                    .values(events)
                    .on_conflict_do_nothing(index_elements=["domain", "timestamp", "event_type"])
                )
                session.commit()
                logger.info(
                    f"{symbol} ({market_group}): {len(events)} events (daily-return std={market_std:.3f}%)"
                )
                total_inserted += len(events)

        logger.info(f"Total: {total_inserted} price events across all markets")
    finally:
        session.close()


def step9_build_event_context(lookback_hours: int = 48) -> None:
    logger.info(f"── Step 9: Building event_context (lookback={lookback_hours}h) ──")
    from datetime import timedelta

    import numpy as np
    from sqlalchemy import select

    from sentiment_signal.db.models import Event, EventContext, Person, SentimentSignalRecord

    session = SessionLocal()
    try:
        events = session.scalars(select(Event)).all()
        logger.info(f"Processing {len(events)} events")

        built = skipped = 0
        for event in events:
            # Skip if already built for this lookback window
            existing = session.scalar(
                select(EventContext).where(
                    EventContext.event_id == event.id,
                    EventContext.lookback_window_hours == lookback_hours,
                )
            )
            if existing:
                skipped += 1
                continue

            window_start = event.timestamp - timedelta(hours=lookback_hours)
            signals = session.scalars(
                select(SentimentSignalRecord).where(
                    SentimentSignalRecord.timestamp >= window_start,
                    SentimentSignalRecord.timestamp <= event.timestamp,
                    SentimentSignalRecord.statement_sentiment.isnot(None),
                )
            ).all()

            if not signals:
                continue

            # Priority: sharpe_analog > hawkish_score > statement_sentiment
            signal_values = [
                s.sharpe_analog
                if s.sharpe_analog is not None
                else s.hawkish_score
                if s.hawkish_score is not None
                else s.statement_sentiment
                for s in signals
            ]
            mean_signal = float(np.mean(signal_values))

            # Dominant person — most statements in the window
            person_counts: dict[str, int] = {}
            for sig in signals:
                pid = str(sig.person_id)
                person_counts[pid] = person_counts.get(pid, 0) + 1
            dominant_pid = max(person_counts, key=person_counts.get)
            dominant_person_obj = session.get(Person, dominant_pid)
            dominant_person = dominant_person_obj.canonical_name if dominant_person_obj else None

            ctx = EventContext(
                event_id=event.id,
                statement_ids=[sig.statement_id for sig in signals],
                sentiment_signal_ids=[sig.id for sig in signals],
                lookback_window_hours=lookback_hours,
                mean_signal_in_window=mean_signal,
                dominant_person=dominant_person,
            )
            session.add(ctx)
            built += 1

        session.commit()
        logger.info(f"Built {built} event_context rows ({skipped} already existed)")
    finally:
        session.close()


STEPS = {
    1: step1_seed_persons,
    2: step2_scrape_fed,
    3: step3_score_statements,
    4: step4_compute_signals,
    5: step5_fetch_prices,
    6: step6_fetch_macro,
    7: step7_fetch_ecb,
    8: step8_detect_events,
    9: step9_build_event_context,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 pipeline")
    parser.add_argument(
        "--steps",
        default="1,2,3,4,5,6,7,8,9",
        help="Comma-separated step numbers to run (default: all)",
    )
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument(
        "--threshold-mode",
        choices=["pct", "sigma"],
        default="pct",
        help="Step 8 event detection: fixed-percent (pct) or volatility z-score (sigma)",
    )
    parser.add_argument(
        "--sigma",
        type=float,
        default=2.0,
        help="Step 8 sigma cutoff when --threshold-mode=sigma (default 2.0)",
    )
    args = parser.parse_args()

    steps_to_run = [int(s.strip()) for s in args.steps.split(",")]
    for n in steps_to_run:
        fn = STEPS.get(n)
        if fn is None:
            logger.warning(f"Unknown step {n}, skipping")
            continue
        if n == 2:
            fn(start_year=args.start_year)
        elif n == 8:
            fn(threshold_mode=args.threshold_mode, sigma=args.sigma)
        else:
            fn()

    logger.info("Phase 1 complete. Open the dashboard to inspect results:")
    logger.info("  streamlit run sentiment_signal/dashboard/app.py")


if __name__ == "__main__":
    main()
