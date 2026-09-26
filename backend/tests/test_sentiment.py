"""Sentiment: label mapping and which text gets analysed. (The model itself is not loaded here.)"""

from sqlalchemy.dialects import postgresql

from app.retrieval.evidence import sentiment_of
from app.sentiment.model import to_sentiment
from app.sentiment.pipeline import SET_SENTIMENT, needs_sentiment, sentiment_text


def test_confident_answers_keep_their_label():
    assert to_sentiment({"label": "positive", "score": 0.99}, 0.75).label == "positive"
    assert to_sentiment({"label": "negative", "score": 0.91}, 0.75).label == "negative"
    assert to_sentiment({"label": "LABEL_1", "score": 0.95}, 0.75).label == "negative"  # unnamed labels


def test_unsure_answers_are_neutral():
    result = to_sentiment({"label": "positive", "score": 0.6}, 0.75)
    assert result.label == "neutral" and result.score == 0.6


def test_what_gets_analysed():
    assert sentiment_text("whatsapp", "Super da machan!", {}) == "Super da machan!"
    assert sentiment_text("whatsapp", "k", {}) is None  # too short
    assert sentiment_text("audio", "[audio] note.mp3", {}) is None  # no transcript: just a file name
    # Photos: only the user's ingested caption — never the file name, never the picture.
    assert sentiment_text("image", "[photo] a.jpg", {}) is None
    assert sentiment_text("image", "x", {"caption": "draft", "caption_ingested": "Goa trip, semma fun"}) == "Goa trip, semma fun"


def test_evidence_sentiment():
    assert sentiment_of({"sentiment": {"label": "positive", "score": 0.9, "model": "m"}}).label == "positive"
    assert sentiment_of({"sentiment": {"label": "none", "score": None}}) is None
    assert sentiment_of({}) is None and sentiment_of(None) is None


def test_sql_compiles():
    dialect = postgresql.dialect()
    assert "||" in str(SET_SENTIMENT.compile(dialect=dialect))
    assert "#>>" in str(needs_sentiment("m").compile(dialect=dialect))  # meta #>> '{sentiment,model}'
