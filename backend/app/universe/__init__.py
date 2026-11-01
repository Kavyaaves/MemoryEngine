"""The Memory Universe: your memories arranged as a 3D world you can walk through.

    Universe → years (along the time river) → Memory Books (events) → Memory Pages → memories

Everything here is *derived* from the memories table and never changes it:

    layout.py       where a book floats (pure math, stable forever)
    matching.py     which book a page belongs to (pure: attach to an existing book or start one)
    pages.py        put new memories on pages; recount changed pages          (SQL)
    books.py        create books; recount changed books                        (SQL)
    graph.py        person → book and book → book edges (Graph RAG)            (SQL)
    titles.py       auto titles, and grounded AI titles/summaries              (SQL + OpenAI)
    changes.py      the change feed the Memories page polls                    (SQL)
    connections.py  "visit connected memory": same person, similar, earlier…   (SQL, on demand)
    updater.py      the incremental update run after each import

Build the universe for memories imported before it existed (safe to re-run; only unplaced
memories are processed):

    python -m app.universe            # place memories, then name up to 40 books with AI
    python -m app.universe titles     # only name books
"""
