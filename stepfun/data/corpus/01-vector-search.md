Vector search compares a query embedding with stored document embeddings using a distance metric.
seekdb defaults to cosine distance for dense vectors. Approximate indexes such as HNSW trade a small
amount of recall for a large reduction in latency, which matters when a browser sends one query at a time.
