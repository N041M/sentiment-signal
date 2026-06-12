"""Collector for ECB Statistical Data Warehouse (SDW) macro series.

Uses the ECB's public SDMX REST API — no authentication required.
API docs: https://data-api.ecb.europa.eu/service/

Series are stored with an 'ECB_' prefix in macro_data.series_id to
distinguish them from FRED series in the same table.
"""

from __future__ import annotations

import io
import re
import time
from datetime import datetime

import httpx
import pandas as pd
from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from sentiment_signal.db.models import MacroData

BASE_URL = "https://data-api.ecb.europa.eu/service/data"
REQUEST_DELAY = 1.0  # seconds between requests

# (storage_id, dataflow/key, human description)
ECB_SERIES: list[tuple[str, str, str]] = [
    # Key ECB policy rates
    ("ECB_DFR", "FM/B.U2.EUR.4F.KR.DFR.LEV", "ECB Deposit Facility Rate"),
    ("ECB_MRO", "FM/B.U2.EUR.4F.KR.MRR_FR.LEV", "ECB Main Refinancing Operations Rate"),
    ("ECB_MLF", "FM/B.U2.EUR.4F.KR.MLFR.LEV", "ECB Marginal Lending Facility Rate"),
    # Inflation
    ("ECB_HICP", "ICP/M.U2.N.000000.4.ANR", "Eurozone HICP Inflation YoY"),
    # Money supply
    ("ECB_M3", "BSI/M.U2.N.A.A20.A.1.U2.2240.Z01.E", "Eurozone M3 Money Supply"),
    # Yield curve (AAA Eurozone, proxy for German Bund)
    ("ECB_10Y", "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y", "Eurozone AAA 10Y Spot Rate"),
    ("ECB_2Y", "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y", "Eurozone AAA 2Y Spot Rate"),
]


def fetch_series(
    storage_id: str,
    dataflow_key: str,
    start_period: str = "2015-01",
) -> list[dict]:
    """Fetch one ECB SDW series; return list of macro_data row dicts."""
    url = f"{BASE_URL}/{dataflow_key}"
    try:
        resp = httpx.get(
            url,
            params={"format": "csvdata", "startPeriod": start_period},
            timeout=30,
            follow_redirects=True,
            headers={"Accept": "text/csv"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning(f"ECB SDW {storage_id}: request failed — {exc}")
        return []

    try:
        df = pd.read_csv(io.StringIO(resp.text))
    except Exception as exc:
        logger.warning(f"ECB SDW {storage_id}: CSV parse failed — {exc}")
        return []

    if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
        logger.warning(f"ECB SDW {storage_id}: unexpected columns: {list(df.columns)}")
        return []

    rows = []
    for _, row in df[["TIME_PERIOD", "OBS_VALUE"]].dropna().iterrows():
        ts = _parse_period(str(row["TIME_PERIOD"]))
        if ts is None:
            continue
        try:
            rows.append(
                {
                    "series_id": storage_id,
                    "timestamp": ts,
                    "value": float(row["OBS_VALUE"]),
                }
            )
        except (ValueError, TypeError):
            continue
    return rows


def run_ecb_fetch(session: Session, start_period: str = "2015-01") -> None:
    for storage_id, dataflow_key, description in ECB_SERIES:
        logger.info(f"ECB SDW: fetching {storage_id} ({description})")
        rows = fetch_series(storage_id, dataflow_key, start_period)
        if rows:
            session.execute(
                pg_insert(MacroData)
                .values(rows)
                .on_conflict_do_nothing(index_elements=["series_id", "timestamp"])
            )
            session.commit()
            logger.info(f"  → {len(rows)} rows")
        else:
            logger.warning("  → no data returned")
        time.sleep(REQUEST_DELAY)


def _parse_period(period: str) -> datetime | None:
    """Convert ECB period strings to datetime.

    Handles daily (2015-01-02), monthly (2015-01), quarterly (2015-Q1),
    and annual (2015) formats.
    """
    period = period.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", period):
        try:
            return datetime.strptime(period, "%Y-%m-%d")
        except ValueError:
            return None
    if re.match(r"^\d{4}-\d{2}$", period):
        try:
            return datetime.strptime(period, "%Y-%m")
        except ValueError:
            return None
    m = re.match(r"^(\d{4})-Q(\d)$", period)
    if m:
        month = (int(m.group(2)) - 1) * 3 + 1
        return datetime(int(m.group(1)), month, 1)
    if re.match(r"^\d{4}$", period):
        try:
            return datetime(int(period), 1, 1)
        except ValueError:
            return None
    return None
