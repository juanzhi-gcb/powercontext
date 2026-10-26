A vector index is not necessarily updated on every write. seekdb flushes new rows to the index in the
background, so a document becomes retrievable only after the refresh completes. A client that searches
immediately after a write should confirm the row count or wait for the refresh.
