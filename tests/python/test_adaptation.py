"""Voice adaptation tests."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))


class TestAdaptationStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        os.environ["AFK_DATA_DIR"] = self._tmp

    def test_learned_phrase_applies_to_future_transcripts(self):
        from afk_backend.adaptation import AdaptationStore

        store = AdaptationStore()
        res = store.learn_correction("Pachisia gw", "Pachisia GW")
        self.assertTrue(res["ok"])

        text, changed, applied = store.apply("Send this to Pachisia gw today.")
        self.assertTrue(changed)
        self.assertEqual(text, "Send this to Pachisia GW today.")
        self.assertEqual(applied[0]["intended"], "Pachisia GW")

    def test_learned_correction_persists(self):
        from afk_backend.adaptation import AdaptationStore

        first = AdaptationStore()
        first.learn_correction("kesh of", "Keshav")

        second = AdaptationStore()
        text, changed, _applied = second.apply("Credit kesh of in the docs.")
        self.assertTrue(changed)
        self.assertEqual(text, "Credit Keshav in the docs.")

    def test_clear_resets_learning(self):
        from afk_backend.adaptation import AdaptationStore

        store = AdaptationStore()
        store.learn_correction("af kay", "AFK")
        snapshot = store.clear()
        self.assertEqual(snapshot["correction_count"], 0)


if __name__ == "__main__":
    unittest.main()
