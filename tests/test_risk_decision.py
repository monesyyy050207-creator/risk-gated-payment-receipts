import json

from receipt_image_service import PaymentEvent, ReceiptWorkflow


class RecordingGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *, prompt: str, idempotency_key: str) -> bytes:
        self.calls += 1
        return b"png"


def test_high_risk_payment_is_held_without_generating_image(tmp_path):
    generator = RecordingGenerator()
    workflow = ReceiptWorkflow(generator, tmp_path)
    event = PaymentEvent(
        event_id="pay_review_204",
        amount="900.00",
        currency="USD",
        merchant_name="Atlas Parts",
        risk_score=82,
    )

    result = workflow.handle(event)
    repeated = workflow.handle(event)

    assert result.action == "manual_review"
    assert repeated.action == "manual_review"
    assert result.image_path is None
    assert generator.calls == 0
    audit_lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert len(audit_lines) == 1
    audit = json.loads(audit_lines[0])
    assert audit["event_id"] == "pay_review_204"
    assert audit["action"] == "manual_review"
    assert len(audit["digest"]) == 64
