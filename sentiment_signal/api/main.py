from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from sentiment_signal.db.models import Event, EventContext, Person, SentimentSignalRecord
from sentiment_signal.db.session import get_session

app = FastAPI(title="Sentiment Signal", version="0.1.0")


@lru_cache(maxsize=1)
def get_pipeline():
    """Load the NLP pipeline once and reuse it across requests.

    Lazily instantiated on first /analyze call so app startup stays fast and the
    438 MB model is only loaded if the endpoint is actually used.
    """
    from sentiment_signal.nlp.pipeline import NLPPipeline

    return NLPPipeline()


@app.get("/signal/latest")
def signal_latest(limit: int = 20, session: Session = Depends(get_session)):
    rows = session.scalars(
        select(SentimentSignalRecord).order_by(SentimentSignalRecord.timestamp.desc()).limit(limit)
    ).all()
    return [
        {"id": str(r.id), "timestamp": r.timestamp, "sharpe_analog": r.sharpe_analog} for r in rows
    ]


@app.get("/signal/{person_name}")
def signal_by_person(person_name: str, limit: int = 50, session: Session = Depends(get_session)):
    person = session.scalar(select(Person).where(Person.canonical_name == person_name))
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    rows = session.scalars(
        select(SentimentSignalRecord)
        .where(SentimentSignalRecord.person_id == person.id)
        .order_by(SentimentSignalRecord.timestamp.desc())
        .limit(limit)
    ).all()
    return rows


@app.get("/prediction/{domain}")
def prediction_by_domain(domain: str, session: Session = Depends(get_session)):
    latest_event = session.scalar(
        select(EventContext)
        .join(Event, EventContext.event_id == Event.id)
        .where(Event.domain == domain)
        .order_by(EventContext.computed_at.desc())
    )
    if latest_event is None:
        raise HTTPException(status_code=404, detail="No predictions found for domain")
    return {
        "domain": domain,
        "direction": latest_event.model_prediction_direction,
        "magnitude": latest_event.model_prediction_magnitude,
        "was_correct": latest_event.was_correct,
    }


@app.get("/event/{event_id}/context")
def event_context(event_id: str, session: Session = Depends(get_session)):
    ctx = session.scalar(select(EventContext).where(EventContext.event_id == event_id))
    if ctx is None:
        raise HTTPException(status_code=404, detail="Event context not found")
    return ctx


@app.post("/analyze")
def analyze(text: str):
    # analyze_documents chunks long text and aggregates, so the full document is scored
    result = get_pipeline().analyze_documents([text])[0]
    return {
        "sentiment_score": result["sentiment_score"],
        "sentiment_label": result["sentiment_label"],
        "probs": result["probs"],
        "embedding_dim": len(result["embedding"]),
        "n_chunks": result["n_chunks"],
    }
