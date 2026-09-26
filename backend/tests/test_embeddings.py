from app.ai.embeddings import embedding_text, is_permanent, query_embedding_text
from app.ai.providers.base import AIUnavailable
from app.ingestion.records import ParsedRecord
from app.multilingual.tanglish import process_text


def test_backfill_stops_on_errors_that_waiting_cannot_fix():
    assert is_permanent(AIUnavailable("openai: Error code: 401 - {'error': {'code': 'invalid_api_key'}}"))
    assert is_permanent(AIUnavailable("openai: Error code: 429 - {'error': {'code': 'insufficient_quota'}}"))
    assert not is_permanent(AIUnavailable("openai: Error code: 429 - {'error': {'code': 'rate_limit_exceeded'}}"))
    assert not is_permanent(AIUnavailable("openai: Error code: 503 - service unavailable"))


def test_short_chat_messages_are_embedded_with_their_context():
    previous = [ParsedRecord("shall we go to kerala next week?", author="Rahul"),
                ParsedRecord("yes! booking tickets", author="Me")]
    record = ParsedRecord("seri da", author="Rahul")
    text = embedding_text(record, previous, process_text(record.text))
    assert text.startswith("Rahul: seri da")
    assert "kerala" in text and "booking tickets" in text


def test_search_queries_are_embedded_in_the_same_shape_as_memories():
    assert query_embedding_text("SERIIII  Da") == "serii da"  # normalised like stored text
    # A Tamil-script question also carries its Latin-letter spelling, like a stored Tamil message.
    assert query_embedding_text("நான் அவன் கூட போனேன்") == "நான் அவன் கூட போனேன்\nnaan avan kooda ponen"
