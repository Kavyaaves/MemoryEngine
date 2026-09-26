"""Ingestion: uploaded file → parsed records → stored, searchable memories.

    dispatch.py       what kind of file is this? → call the right parser
    parsers/          WhatsApp, Instagram, journals & documents
    records.py        ParsedRecord / ParseResult + content hashes (incremental re-imports)
    pipeline.py       the job runner: runs every step below in order
    writer.py         saves sources, conversations and memories
    graph_builder.py  adds "who talks to whom" edges to the knowledge graph
    media.py          stores photos/audio/video; transcribes audio with AI
    photos.py         photo metadata (name, dates — never the picture) and user captions
"""
