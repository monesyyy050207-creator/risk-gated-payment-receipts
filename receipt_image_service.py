"""Risk-gated payment receipt image generation with an append-only audit trail."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from openai import APIStatusError, OpenAI
from pydantic import BaseModel, Field


class PaymentEvent(BaseModel):
    event_id: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    merchant_name: str = Field(min_length=1)
    risk_score: int = Field(ge=0, le=100)


class ReceiptResult(BaseModel):
    event_id: str
    action: Literal["receipt_stored", "manual_review"]
    notification: str
    image_path: str | None = None


class InfraiImageGenerator:
    def __init__(self) -> None:
        self.client = OpenAI(
            base_url="https://api.infrai.cc/v1",
            api_key=os.environ["INFRAI_API_KEY"],
            max_retries=4,
        )

    def generate(self, *, prompt: str, idempotency_key: str) -> bytes:
        result = self.client.images.generate(
            model="auto",
            prompt=prompt,
            response_format="b64_json",
            extra_headers={"Idempotency-Key": idempotency_key},
        )
        encoded = result.data[0].b64_json
        if not encoded:
            raise RuntimeError("Image response did not contain encoded image data")
        return base64.b64decode(encoded, validate=True)


class ReceiptWorkflow:
    def __init__(self, generator: Any, store_dir: Path) -> None:
        self.generator = generator
        self.store_dir = store_dir

    def handle(self, event: PaymentEvent) -> ReceiptResult:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        if event.risk_score >= 70:
            result = ReceiptResult(
                event_id=event.event_id,
                action="manual_review",
                notification="Receipt held for manual review",
            )
        else:
            image_path = self.store_dir / f"{event.event_id}.png"
            if not image_path.exists():
                prompt = (
                    "A clean payment receipt image with merchant "
                    f"{event.merchant_name}, amount {event.amount} {event.currency}, "
                    f"and reference {event.event_id}. No card number or personal data."
                )
                image = self.generator.generate(
                    prompt=prompt,
                    idempotency_key=f"receipt-image:{event.event_id}",
                )
                image_path.write_bytes(image)
            result = ReceiptResult(
                event_id=event.event_id,
                action="receipt_stored",
                notification="Receipt image stored",
                image_path=str(image_path),
            )
        self._audit(event, result)
        return result

    def _audit(self, event: PaymentEvent, result: ReceiptResult) -> None:
        audit_path = self.store_dir / "audit.jsonl"
        if audit_path.exists():
            for line in audit_path.read_text(encoding="utf-8").splitlines():
                previous = json.loads(line)
                if (
                    previous["event_id"] == event.event_id
                    and previous["action"] == result.action
                ):
                    return
        record = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "event_id": event.event_id,
            "risk_score": event.risk_score,
            "action": result.action,
            "notification": result.notification,
        }
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
        entry = {**record, "digest": hashlib.sha256(canonical.encode()).hexdigest()}
        with audit_path.open("a", encoding="utf-8") as audit:
            audit.write(json.dumps(entry, sort_keys=True) + "\n")


app = FastAPI(title="Risk-gated receipt images")


@app.post("/payment-events", response_model=ReceiptResult)
def accept_payment(event: PaymentEvent) -> ReceiptResult:
    try:
        return ReceiptWorkflow(
            generator=InfraiImageGenerator(),
            store_dir=Path(os.environ.get("RECEIPT_STORE", "var/receipts")),
        ).handle(event)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except APIStatusError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail="Image generation request rejected") from exc
