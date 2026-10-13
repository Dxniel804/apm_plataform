# Reading a receipt with a local model (OCR)

Code: `apps/api/app/ocr/` (the route, the provider, the limits), `apps/ocr/` (the service that runs the model), `docker-compose.yml` (profile `ocr`). The reading is a **suggestion for the expense form**: it never creates an expense, never stores the photo and never decides anything. If it is off, slow or wrong, the person types the expense by hand, as before.

## How it works

```
browser ──photo──▶ API (apps/api) ──photo──▶ OCR service (apps/ocr, private network, no internet)
   ▲                 authenticates, checks           reads the photo with a local model,
   │                 permission, type and size,      finds the total, the date, the CNPJ and
   │                 limits the rate                 the shop in the text
   └─ suggestion ◀── validates every field ◀─ JSON ──┘
```

1. The funcionário opens "Nova despesa" and chooses "Ler a nota (OCR)", takes or chooses ONE photo.
2. `POST /api/v1/schools/{school_id}/expenses/ocr` (multipart `file`; permission `expenses:submit`, like creating the expense). The API refuses what it can refuse cheaply (the feature is off, the size, the type read from the bytes, too many requests), then asks the OCR service.
3. The service reads the photo and answers `{fields: {total_cents, date, merchant, document_number}, model, elapsed_ms}`, each field with a `value` and a `confidence` from 0 to 1. A field it did not find is absent.
4. The API **validates each field** (an amount between R$ 0,01 and R$ 1.000.000,00, a date that is not in the future nor older than three years, a short clean text, a well-formed document number) and drops what fails. It answers `{amount_cents, occurred_on, vendor, document_number, confidence: {amount, date, vendor, document}, model, elapsed_ms}`; every field may be `null`. **The text of the receipt is never returned**: it may hold a CPF or a card number.
5. The form fills the fields marked "sugerido: confira" (the doubtful ones, below 0.6, ask for extra attention). The person edits what is wrong and saves. The same photo is attached as the `INVOICE` of the expense through the usual upload (a second upload of the same bytes: no state on the server).

`GET /api/v1/schools/{school_id}/expenses/ocr` answers `{enabled}`, so the form only offers the reading when it is on.

## Errors the form survives

| Status | `code` | Meaning | What the site does |
| --- | --- | --- | --- |
| 503 | `ocr_unavailable` | the feature is off, or the service is down, refused the secret or answered something that is not its contract | "fill by hand", the photo is kept as the attachment |
| 503 | `ocr_busy` | every slot is taken (`Retry-After: 5`) | same, with "try again" |
| 504 | `ocr_timeout` | the model took more than `OCR_TIMEOUT_SECONDS` | same |
| 429 | `rate_limited` | more than `OCR_USER_PER_MINUTE` readings by this person in a minute (`Retry-After`) | wait |
| 415, 413, 411, 422 | `attachment_type_not_allowed`, `payload_too_large`, `length_required`, `validation_error` | not a PNG, JPEG or WebP photo, too big, no declared size, empty | the usual messages |

Each reading writes one audit event `expense.ocr_requested` (`outcome`, `size_bytes`, the names of the fields found, the model): never the photo and never its text.

## The OCR service (`apps/ocr`)

`POST /v1/extract`: the photo is the **body** (`Content-Type: image/png|jpeg|webp`), `Authorization: Bearer <OCR_TOKEN>`. `GET /health` for the container. No other route, no documentation page.

- **Image**: the type is declared, the bytes must be that image (Pillow opens and loads it), at most `OCR_MAX_BYTES` (10 MiB) and `OCR_MAX_PIXELS` (50 million; a bigger image is refused before it is decompressed).
- **Text to fields**: `ocr_service/parser.py` is pure Python with no model: total (next to "VALOR A PAGAR", "VALOR TOTAL", "TOTAL"; never the change, the subtotal or the taxes), date (next to "EMISSÃO"/"DATA" when it can), CNPJ (the two check digits are verified) and the shop (the line above the CNPJ). It says how sure it is: 0.9 next to a label or with valid check digits, 0.7 a single candidate, 0.4 to 0.5 a guess. It does not invent: nothing found, nothing returned.
- **Engines** (`OCR_ENGINE`): `stub` (reads nothing: the chain can be tried without a model), `demo` (always the same made-up receipt, for the form and the browser tests; **refused with `ENV=production`**) and `huggingface` (`transformers` `image-to-text` over a model that was DOWNLOADED beforehand: `OCR_MODEL_ID` and a pinned `OCR_MODEL_REVISION`, never `main`; no remote code, no network).
- **One photo at a time** (a lock); the API also limits how many readings run at once per API process (`OCR_MAX_CONCURRENCY`) and how many a person asks per minute. Both limits are in the memory of each API process: with N processes the ceiling is N times the limit. The service is the real bottleneck.
- Nothing is stored and nothing of the photo or of the text is logged (one line per reading: how many fields, how long).

## Running it

```
# .env: OCR_ENABLED=true  OCR_TOKEN=$(openssl rand -hex 32)  (and OCR_ENGINE=demo to see the form fill itself)
docker compose --profile ocr up -d --build api ocr
```

`ocr` is **not started by `docker compose up`** (it is heavy). It is on the private network `ocr_net` (`internal: true`: containers on it reach each other and nothing else), publishes no port, runs as a user with no privileges (uid 10001) on a read-only filesystem with all capabilities dropped, and reads models only from the read-only volume `ocr_models`. Tested: from inside the container `https://example.com` is unreachable and the API reaches `http://ocr:8080/health`.

The browser test (`apps/web/e2e/ocr.spec.ts`) runs the whole chain (browser, API, OCR service) with `OCR_ENGINE=demo`, against a throwaway database: it checks that the photo goes out, the form fills as a suggestion, a field loses its mark when the person edits it, and that the same photo is attached on save. It is **skipped** when the server has the reading off. It says nothing about the accuracy of a model.

### Putting a real model in (the part that depends on the chosen model)

1. Pick the model with real photos: about 30 receipts of the school (no personal data), a few candidates, the fields each one gets right. The parser is shared, so the comparison is only about the text each model reads. Which model, and whether the server has a GPU, is the decision of this spike.
2. Download it **once**, outside the container, into the `ocr_models` volume (with the revision you reviewed) and note the commit hash.
3. `.env`: `OCR_ENGINE=huggingface`, `OCR_INSTALL_HF=1`, `OCR_MODEL_ID`, `OCR_MODEL_REVISION`; rebuild `ocr`. A model that does not fit `image-to-text` (a different pipeline) is a new class in `ocr_service/engines.py` with the same one method, `read(image) -> text`.

## Accepted risks and limits

- **The answer of the model is untrusted data** and is validated field by field, but a wrong amount that is in range is still a wrong amount: that is why it is a suggestion the person confirms, with the confidence shown, and why the manager still approves the expense with the attached receipt in front of them.
- A photo is processed by the model (an image decoder: Pillow, and PyTorch when a model is installed). The container is isolated for that reason (no network, no privileges, read-only), the image is bounded in bytes and pixels, and the model comes from a pinned revision without remote code.
- The limits per process (above); no queue: a busy reading answers `ocr_busy` instead of waiting long.
