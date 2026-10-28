from nullpath.context import artifact_ref


def test_artifact_ref_reads_list_and_artifact_payload_shapes():
    assert artifact_ref({"artifact": {"artifact_id": "art_1", "revision": 2}}) == {
        "artifact_id": "art_1",
        "revision": 2,
    }
    assert artifact_ref({"artifact_id": "art_2", "revision": 3, "content": {}}) == {
        "artifact_id": "art_2",
        "revision": 3,
    }
