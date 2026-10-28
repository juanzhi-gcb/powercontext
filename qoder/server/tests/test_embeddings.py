import math

from nullpath.embeddings import HashingEmbedder


def test_hashing_embedding_is_reproducible_and_normalized():
    embedder = HashingEmbedder()
    text = "机制 mechanism / reliability and complementarity"
    first = embedder.embed(text)
    second = embedder.embed(text)
    assert first == second
    assert len(first) == 64
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0, abs_tol=1e-6)


def test_hashing_embedding_distinguishes_changed_mechanism():
    embedder = HashingEmbedder()
    original = embedder.embed("Broad phase diagram across tasks and models")
    changed = embedder.embed("Unidentifiable observation map under a restricted control statistic")
    assert original != changed
