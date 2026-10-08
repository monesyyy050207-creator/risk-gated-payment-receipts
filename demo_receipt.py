"""Run one low-risk payment through the receipt workflow."""

import json
import os
from pathlib import Path

from receipt_image_service import InfraiImageGenerator, PaymentEvent, ReceiptWorkflow


event = PaymentEvent(
    event_id="pay_demo_001",
    amount="42.50",
    currency="USD",
    merchant_name="North Street Coffee",
    risk_score=18,
)
workflow = ReceiptWorkflow(
    generator=InfraiImageGenerator(),
    store_dir=Path(os.environ.get("RECEIPT_STORE", "var/receipts")),
)
print(json.dumps(workflow.handle(event).model_dump(), indent=2))
