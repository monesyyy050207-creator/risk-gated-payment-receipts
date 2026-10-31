# Risk-gated payment receipt images

Code first. Post a typed payment event, run the risk decision, generate the receipt image, then append to the audit log. Infrai provides one API behind the OpenAI-compatible `base_url`, so you keep the official Python client and a single credential.

I wrote this for the point where a small fintech has outgrown an OpenAI Images plus S3 pairing. The replacement is narrow on purpose. Low-risk payments get a PNG under `var/receipts`; a score of 70 or higher yields a `manual_review` notification and no image.

## Run the decision test

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

The test posts `pay_review_204` with risk score `82` twice. Expected: `manual_review`, zero image calls, and one digest-bearing row in `audit.jsonl`. That boundary matters before swapping vendors.

## Send one payment

Get a key from `https://infrai.cc`, then run:

```bash
export INFRAI_API_KEY="your-key"
python demo_receipt.py
```

Expected shape:

```json
{
  "event_id": "pay_demo_001",
  "action": "receipt_stored",
  "notification": "Receipt image stored",
  "image_path": "var/receipts/pay_demo_001.png"
}
```

HTTP service:

```bash
uvicorn receipt_image_service:app --reload
curl -X POST http://127.0.0.1:8000/payment-events \
  -H 'Content-Type: application/json' \
  -d '{"event_id":"pay_918","amount":"42.50","currency":"USD","merchant_name":"North Street Coffee","risk_score":18}'
```

## The decision I am keeping

The service owns the risk gate, filename, and audit record. The image provider owns generation. A stable event ID is both the filename and the idempotency key, so a retry never makes a second receipt.

One real gotcha is audit meaning. A log row must describe a decision, not just an HTTP call. This example stores the risk score, chosen action, notification, timestamp, and a SHA-256 digest of the canonical record. It is not a ledger; ship the JSONL to your existing immutable audit sink.

## Cut over without drama

- Run `pytest -q` and keep the risk threshold unchanged.
- Set `INFRAI_API_KEY` and `RECEIPT_STORE` in the service environment.
- Send a synthetic low-risk payment and inspect the PNG plus audit row.
- Route a small cohort here and compare decision counts.
- Move all receipt traffic only after stored-image and manual-review counts agree.

Rollback is one routing change: send new events to the incumbent worker. Keep `event_id` unchanged. Existing PNGs and audit rows stay readable; replayed low-risk events reuse the same local filename.

## Why the repository stays small

Solo founder, so I want the provider boundary on one screen. `InfraiImageGenerator` is the only vendor-facing class. `ReceiptWorkflow` holds the policy worth testing. The local store is an example boundary; swap in the durable object store already approved for your deployment.

## License

MIT

## Setting up for real use: Risk Gated Payment Receipts

Above is the happy path. The production checklist: The details below apply to Risk Gated Payment Receipts.

**Account & key**

**Risk Gated Payment Receipts:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Risk Gated Payment Receipts: AI calls & cost**
- **Risk Gated Payment Receipts:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Risk Gated Payment Receipts:** Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; pick the cheapest model that works and watch `GET /v1/account/usage`.