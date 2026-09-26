"""Sentiment: is a memory happy, sad, or neither? (a local Tamil/Tanglish model)

    model.py      the TamilSense model from Hugging Face, loaded once: classify(texts) → labels
    pipeline.py   which memories to analyse, and saving the results in memory.meta["sentiment"]
    __main__.py   analyse everything still missing:  python -m app.sentiment

It hooks into the rest of the app in four places:
    ingestion/pipeline.py   new memories are analysed right after an import (step 7)
    ingestion/photos.py     photos are analysed when their caption is ingested
    api/sentiment.py        mood over time (Life + People pages), status + "analyse now" (AI Lab)
    retrieval/evidence.py   every Evidence card carries its memory's sentiment

The model runs on this machine's CPU: no text is sent anywhere, and it costs nothing per message.
"""
