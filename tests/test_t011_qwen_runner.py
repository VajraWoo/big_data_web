import json
import tempfile
import unittest
from pathlib import Path

from pipelines.run_t011_qwen import (
    build_direct_messages,
    format_insight,
    load_successful_input_ids,
    split_insights,
    validate_suggestion,
)


class CharacterTokenizer:
    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        assert tokenize is True
        assert add_generation_prompt is True
        return list("".join(message["content"] for message in messages))


class BatchEncodingLike:
    def __init__(self, input_ids):
        self.input_ids = input_ids

    def __len__(self):
        return 2


class BatchEncodingTokenizer:
    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        return BatchEncodingLike([1, 2, 3, 4, 5])


def input_row() -> dict:
    return {
        "input_id": "input-1",
        "parent_asin": "p1",
        "product_title": "Countertop ice maker",
        "product_category": "Ice Makers",
        "taxonomy_id": "t1",
        "canonical_theme_name": "Noise level",
        "negative_insight_count": 3,
        "mixed_insight_count": 0,
        "support_insight_count": 3,
        "support_review_count": 3,
        "insights": [
            {"candidate_id": "a", "review_id": "r1", "polarity": "negative", "candidate_text": "noise: loud fan"},
            {"candidate_id": "b", "review_id": "r2", "polarity": "negative", "candidate_text": "noise: rattles"},
            {"candidate_id": "c", "review_id": "r3", "polarity": "negative", "candidate_text": "noise: grinding sound"},
        ],
    }


class T011QwenRunnerTests(unittest.TestCase):
    def test_token_count_reads_input_ids_from_batch_encoding(self) -> None:
        from pipelines.run_t011_qwen import token_count

        self.assertEqual(5, token_count(BatchEncodingTokenizer(), build_direct_messages(input_row())))

    def test_format_includes_distinct_raw_evidence_without_duplication(self) -> None:
        insight = {
            "candidate_id": "a",
            "polarity": "negative",
            "candidate_text": "noise: the fan is loud",
            "evidence": "the fan is loud",
        }
        formatted = format_insight(insight)
        self.assertIn("noise: the fan is loud", formatted)
        self.assertIn("原始证据：the fan is loud", formatted)

        insight["evidence"] = insight["candidate_text"]
        self.assertEqual(1, format_insight(insight).count("noise: the fan is loud"))

    def test_direct_prompt_contains_each_insight_once(self) -> None:
        messages = build_direct_messages(input_row())
        prompt = "\n".join(message["content"] for message in messages)

        for candidate_id in ("a", "b", "c"):
            self.assertEqual(1, prompt.count(f"[{candidate_id}]"))

    def test_sequential_chunks_preserve_all_insights_exactly_once(self) -> None:
        row = input_row()
        chunks = split_insights(row, CharacterTokenizer(), max_input_tokens=220)
        emitted = [insight["candidate_id"] for chunk in chunks for insight in chunk]

        self.assertGreater(len(chunks), 1)
        self.assertEqual(["a", "b", "c"], emitted)

    def test_resume_skips_success_but_retries_failed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.ndjson"
            checkpoint.write_text(
                json.dumps({"input_id": "done", "generation_status": "success"}) + "\n"
                + json.dumps({"input_id": "retry", "generation_status": "failed"}) + "\n",
                encoding="utf-8",
            )

            self.assertEqual({"done"}, load_successful_input_ids(checkpoint))

    def test_suggestion_contract_accepts_one_nonempty_field(self) -> None:
        self.assertEqual(
            "Reduce vibration at the fan mount.",
            validate_suggestion({"improvement_suggestion": " Reduce vibration at the fan mount. "}),
        )
        with self.assertRaises(ValueError):
            validate_suggestion({"improvement_suggestion": "", "extra": "not allowed"})


if __name__ == "__main__":
    unittest.main()
