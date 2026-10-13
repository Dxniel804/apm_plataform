# Campaigns (Personalização: produtos e carrinho)

Code: `apps/api/app/campaigns/` (what the management writes: router, service, repository, schemas), `apps/api/app/public/campaigns.py` and `campaign_service.py` (what the families see and the order), `apps/api/app/storage/image_clean.py` (the pictures), migration `0013_campaigns.py`, models in `app/models/campaigns.py`.

The management creates a **campaign** (a party, a kit): a title, a text, a cover and **products** with a name, a text, a picture, a price and an optional limit per order. The family picks quantities on the public page of the school, sees the total and pays by Pix. The revenue goes to the ledger under its own category, **Vendas de campanha** (`campaign_sales`, report group `OTHER_INCOME`), so the closing report shows it as its own line, apart from the contributions of the parents.

## The rule that matters: the page never decides the money

The order the family sends has **which products and how many**, never a price or a total. The server reads the current price of every product, adds them up and creates the contribution with that amount. And the database refuses anything else, whatever the code above does:

| Where | Rule |
| --- | --- |
| `contribution_items_20_item` (before each line) | the product is on sale **now** (campaign ACTIVE and inside its dates in the school's time zone, product active, quantity within its limit) and the copy is its **current** name and price |
| `contribution_items_90_total` and `contributions_90_campaign_total` (at COMMIT) | the amount of a contribution of a campaign is exactly the sum of its items, it has at least one, and they all belong to the campaign of the contribution; a contribution without a campaign has no items |
| `contribution_items` | insert-only: the copy (name, unit price, quantity) never changes and is never removed, so a price changed later never touches an order already made |

Limits: a product costs R$ 1,00 to R$ 10.000,00; at most 99 of a product per line and 20 lines per order; an order adds up to at most R$ 50.000,00; a campaign has at most 50 products.

## Who may do what

`campaigns:manage` (the `treasurer`, the *gestão*, and `school_admin`) does everything below. Nobody else touches a campaign. The families need no login.

## What the management does: `/api/v1/schools/{school_id}`

| Method and path | What it does |
| --- | --- |
| `POST /campaigns` | Creates a campaign, always a **DRAFT** (nothing is on sale): `title`, optional `description`, `starts_on`, `ends_on` |
| `GET /campaigns` | The campaigns of the school, the ones on sale first, with the counts of products and what the paid orders brought in. `?status=` |
| `GET /campaigns/{id}` | One campaign with its products |
| `PATCH /campaigns/{id}` | Text and dates, while it has not ended (`null` clears an optional field) |
| `POST /campaigns/{id}/activate` | DRAFT to ACTIVE: needs an active product, and an end date that is not past |
| `POST /campaigns/{id}/end` | DRAFT or ACTIVE to ENDED: **final**. Nothing more is sold; the orders already made stay |
| `POST /campaigns/{id}/items` | Adds a product: `name`, optional `description`, `price_cents`, optional `max_per_order`, `position` |
| `PATCH /campaigns/{id}/items/{item_id}` | Changes a product (a new price never touches an order already made). `is_active: false` takes it off the shelf: a product is never removed, because it may have been sold |
| `PUT /campaigns/{id}/image`, `PUT /campaigns/{id}/items/{item_id}/image` | The cover and the picture of a product (multipart `file`: PNG, JPEG or WebP, up to 5 MiB). `DELETE` removes it |
| `GET /campaigns/{id}/image`, `GET /campaigns/{id}/items/{item_id}/image` | The picture, for the management to see (a draft too), `private, no-store` |

The answer to every write is the whole campaign with its products, so the site updates in one go.

## What the families see: `/api/v1/public/schools/{slug}`

| Method and path | What it does |
| --- | --- |
| `GET /campaigns` | The campaigns on sale: ACTIVE, with an active product, and today inside its dates |
| `GET /campaigns/{id}` | One of them with its products and their current prices. A draft, an ended one, one outside its dates and one of another school are **the same `404`** |
| `POST /campaigns/{id}/orders` | `{lines: [{item_id, quantity}], guardian_name, ...}` with an `Idempotency-Key`. Creates the contribution (PENDING_PAYMENT, category `campaign_sales`) and its Pix charge, and answers like `POST /contributions`. From there the polling, the renewal of the charge and the receipt are the same routes (`/contributions/{token}/...`); the **receipt lists what was bought** |
| `GET /campaigns/{id}/cover`, `GET /campaigns/{id}/items/{item_id}/image` | The pictures, public once the campaign is on sale: `ETag` (its sha256) and `Cache-Control: public, max-age=300, must-revalidate`, `nosniff`, `Content-Security-Policy: default-src 'none'; sandbox` |

The same `Idempotency-Key` with the same cart answers with the same order; with another cart it is `409 idempotency_key_reused`. The identification (guardian, student, class, e-mail, phone) follows the settings of the school exactly as in a free-value contribution. No new `SECURITY DEFINER` function was needed: the school comes from the slug through the function of 0008 and the rest runs as `apm_app` under row level security.

### Errors of the order

`application/problem+json` as in [auth.md](auth.md#errors). Besides `404 not_found`, `409 idempotency_key_reused` and `429 rate_limited`:

| Status | `code` | When |
| --- | --- | --- |
| 422 | `validation_error` | `errors[]` has the field and a code: `lines[i].item_id` `unavailable` (not on sale) or `duplicate`, `lines[i].quantity` `over_limit`, `lines` `total_out_of_range`, plus the identification fields |
| 409 | `campaign_changed` | the product changed between our reading and our writing: review the cart |
| 409 | `payment_unavailable` | the school cannot receive Pix (or has no `campaign_sales` category) |

## The pictures

They are **public** once the campaign is on sale, and a photo from a phone carries where and when it was taken. `image_clean.py` rewrites the container of PNG, JPEG and WebP keeping only what is needed to draw it (pixels, colour profile, transparency, animation) and drops the EXIF, the XMP, the comments, the text chunks, the timestamps, the extra images of a multi-picture JPEG and whatever follows the end of the file. It **never decodes the pixels** (no image library to attack): it walks the structure, checks it is well formed, reads the size from the header (at most 8000 px a side and 40 megapixels) and refuses what is not valid. The type is read from the bytes, never from the name or the `Content-Type`. The file is stored under a key made by the server, with the same store as the receipts; the database keeps the key, the type, the size and the sha256.

## In the database

`campaigns`, `campaign_items` and `contribution_items` follow the checklist of [tenancy.md](tenancy.md) and [financial-model.md](financial-model.md): scope and composite foreign keys, every unique index with `school_id`, `created_by_user_id` guarded by `assert_active_member`, write policies that also check the school belongs to the organization, grants by column and no `DELETE`, the final state ENDED frozen, and an audit trail that never copies free text. The service adds one event per action (`campaign.created`, `.updated`, `.activated`, `.ended`, `.item_added`, `.item_updated`, `.image_set`, `.image_cleared`) with ids, states and numbers only. `contributions.campaign_id` is written once with the row and never changes.

## Not done, on purpose

- Editing the suggested amounts and the texts of the free-value page (the columns exist in `school_settings`; the editor is a later step).
- Stock control (a quantity available per product), discounts and coupons, delivery, several campaigns in one cart, and refunding part of an order (a refund is the whole contribution, as before).
- Notifying the management by e-mail when an order is paid.
