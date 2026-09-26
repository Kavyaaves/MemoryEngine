"""The fine-tuning phase (app/finetuning/): the base / derived lineage, the shared training data,
and the first task (address_tagger) — its formats, its evaluation maths, and how the derived
model's stored tags replace the word list in Ask's address counting."""

import json
import uuid
from types import SimpleNamespace

from app.ai.prompts import ADDRESS_TAGGER_SYSTEM
from app.config import Settings
from app.finetuning import data, is_derived, training
from app.finetuning.tasks import TASKS
from app.finetuning.tasks.address_tagger.evaluation import flatten, scores, word_list_tags
from app.finetuning.tasks.address_tagger.labelling import clean_tags, tags_by_number
from app.finetuning.tasks.address_tagger.windows import ChatMessage, first_name, format_window
from app.retrieval.address import AddressReport, tally_address_terms
from app.schemas.ai import AddressTags

DERIVED = "ft:gpt-4.1-nano-2025-04-14:personal:derived:AbC123"


# ---- the lineage: base → derived → derived … ------------------------------------------------

def test_derived_models_are_recognised_by_their_name():
    assert is_derived(DERIVED)
    assert not is_derived("gpt-4.1-nano-2025-04-14") and not is_derived(None) and not is_derived("")


def test_training_starts_from_the_derived_model_once_there_is_one(monkeypatch):
    base = "gpt-4.1-nano-2025-04-14"
    monkeypatch.setattr("app.finetuning.get_settings", lambda: Settings(finetune_derived_model=None))
    assert training.starting_model() == base  # the very first run
    monkeypatch.setattr("app.finetuning.get_settings", lambda: Settings(finetune_derived_model=DERIVED))
    assert training.starting_model() == DERIVED  # every later run continues the same derived model


def test_build_puts_every_task_in_one_training_set(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data, "TRAIN_FILE", tmp_path / "train.jsonl")
    monkeypatch.setattr(data, "VAL_FILE", tmp_path / "val.jsonl")
    record = {"input": "[1] Kavya: Illa kutta", "output": {"messages": [{"id": 1, "address_words": ["kutta"]}]}}
    other_task = SimpleNamespace(SYSTEM_PROMPT="another skill")
    data.write_labels("address_tagger", [record] * 15)
    data.write_labels("other_skill", [record] * 5)

    train, val = data.build({"address_tagger": TASKS["address_tagger"], "other_skill": other_task},
                            progress=lambda _: None)
    assert (train, val) == (16, 4)  # 12 + 4 training, 3 + 1 validation (every 5th is held out)
    prompts = {json.loads(line)["messages"][0]["content"]
               for line in (tmp_path / "train.jsonl").read_text(encoding="utf-8").splitlines()}
    assert prompts == {ADDRESS_TAGGER_SYSTEM, "another skill"}  # each task keeps its own prompt


def test_training_example_is_openai_chat_format():
    record = {"input": "[1] Kavya: Illa kutta", "output": {"messages": [{"id": 1, "address_words": ["kutta"]}]}}
    example = data.training_example(ADDRESS_TAGGER_SYSTEM, record)
    assert [m["role"] for m in example["messages"]] == ["system", "user", "assistant"]
    assert json.loads(example["messages"][2]["content"]) == record["output"]
    assert [i for i in range(10) if data.is_validation(i)] == [4, 9]


# ---- task: address_tagger -------------------------------------------------------------------

def test_address_tagger_is_a_registered_task():
    task = TASKS["address_tagger"]
    assert task.SYSTEM_PROMPT == ADDRESS_TAGGER_SYSTEM and "--person" in task.APPLY_OPTIONS


def test_window_format_is_one_numbered_line_per_message():
    window = [ChatMessage(uuid.uuid4(), "Kavya", "Illa kutta"), ChatMessage(uuid.uuid4(), "Nihal", "Sorry\nkuttaaa")]
    assert format_window(window) == "[1] Kavya: Illa kutta\n[2] Nihal: Sorry kuttaaa"
    assert first_name("Rahul ❤️") == "Rahul" and first_name(None) == "Them"


def test_clean_tags_drops_bad_numbers_empty_lists_and_duplicates():
    raw = AddressTags(messages=[{"id": 2, "address_words": ["kutta", "kutta", " "]}, {"id": 9, "address_words": ["da"]},
                                {"id": 1, "address_words": []}, {"id": 2, "address_words": ["da"]}])
    cleaned = clean_tags(raw, message_count=3)
    assert cleaned.model_dump() == {"messages": [{"id": 2, "address_words": ["kutta", "da"]}]}
    assert tags_by_number(AddressTags(messages=[{"id": 1, "address_words": ["Kuttaaaa"]}])) == {1: {"kuttaa"}}


def test_evaluation_scores_and_the_word_list_baseline():
    gold = flatten(0, {1: {"kutta"}, 2: {"batman"}})  # "batman": a nickname no word list knows
    baseline = flatten(0, word_list_tags(["Illa kutta", "Hi batman", "panni vechen"], ["Kavya", "Nihal"]))
    assert baseline == {(0, 1, "kutta")}
    assert scores(baseline, gold) == {"precision": 1.0, "recall": 0.5, "f1": 0.667}
    assert scores(set(), gold)["f1"] == 0.0


def test_counting_uses_the_derived_models_tags_and_the_word_list_for_the_rest():
    ids = [uuid.uuid4() for _ in range(4)]
    messages = [
        (ids[0], "hi batman", {"model": DERIVED, "words": ["batman"]}),  # new nickname, found by the model
        (ids[1], "panni vechen", {"model": DERIVED, "words": []}),  # model: "did it", not a pet name
        (ids[2], "illa kuttaa", {"model": "ft:an-older-derived-model", "words": ["x"]}),  # old version → word list
        (ids[3], "pothum da", None),  # never tagged → word list
    ]
    terms = {t.term: t for t in tally_address_terms(messages, set(), model=DERIVED)}
    assert terms["batman"].gloss == "found by the derived model"
    assert terms["kutta"].messages == 1 and terms["da"].messages == 1
    assert "x" not in terms and "panni" not in terms

    # Without a derived model everything goes through the word list.
    assert "batman" not in {t.term for t in tally_address_terms(messages, set(), model=None)}


def test_the_fact_line_names_the_base_and_derived_model():
    report = AddressReport("Nihal", "self", True, message_count=100, terms=[], derived_model=DERIVED,
                           tagged_messages=90)
    assert report.used_derived_model
    assert DERIVED in report.method() and "gpt-4.1-nano-2025-04-14" in report.method()
    assert "the other 10" in report.method()
    baseline = AddressReport("Nihal", "self", True, message_count=100, terms=[])
    assert not baseline.used_derived_model and "word list" in baseline.method()
