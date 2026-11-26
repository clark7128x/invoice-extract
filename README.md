# invoice-extract

LLM extraction of structured data from Ukrainian invoice texts: JSON validated by a pydantic schema, retries that feed validation errors back to the model, and a comparison of two models on a synthetic set.
 
The pipeline takes the text of an invoice and returns the supplier, number, date, currency, total, VAT and a list of line items. The model's reply goes through validation. If it fails, the model receives the list of errors with field paths (for example `items.0.quantity`) and corrects its JSON. At most two retries.
 
Missing data gets special attention: when an invoice has no VAT, the field must be `null`, not an invented number. Invented values are counted as a separate metric.
 
## Schema
 
```json
{
  "supplier": "ТОВ «Крига Софт»",
  "number": "INV-2024-0001",
  "date": "2024-05-10",
  "currency": "UAH",
  "total": 1200.0,
  "vat": 200.0,
  "items": [{"name": "Технічна підтримка", "quantity": 2.0, "unit_price": 500.0}]
}
```
 
Validators normalize values before the schema checks them. "10 травня 2024 року" becomes `2024-05-10`, "1 200,00 грн" becomes `1200.0`, "грн" and "₴" become `UAH`, and "Без ПДВ" or "н/д" in the `vat` field becomes `null`. A value that cannot be recognized goes to a retry together with an explanation.
 
## Quick start without keys
 
Requires Python 3.11 or newer.
 
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python generate_data.py
pytest -q
```
 
`generate_data.py` creates `data/invoices.jsonl`: 150 invoices with a fixed seed.
 
## Running with a model
 
The client works with any OpenAI-compatible `/chat/completions` endpoint, including a local server. There are no default model names.
 
```bash
cp .env.example .env
# set LLM_API_BASE, LLM_API_KEY, LLM_MODEL_SMALL, LLM_MODEL_LARGE
set -a; source .env; set +a   # .env is not loaded automatically
 
python extract.py invoice.txt --model small   # one invoice from a file
cat invoice.txt | python extract.py           # or from stdin
 
python eval.py                                # both models on the whole set
python eval.py --models small --limit 20
```
 
If no models are configured, `eval.py` does not crash: the report shows "not measured" for them, with the reason.
 
## Data
 
The set is synthetic, and that shaped the design of the evaluation. A correct JSON is generated first, and the text is rendered from it. The labels are therefore exact, with no manual work and no disagreement between annotators.
 
The text is rendered in five templates: different date and amount formats, tables and free prose, noise lines (IBAN, phone, "Forwarded message") and typos in alphabetic words. Numbers, dates and invoice numbers are never distorted. Some invoices have no VAT; their share is set in `config.yaml`.
 
Synthetic data gives a fair comparison of two models on identical input. It does not show how the system behaves on scans, PDFs and real supplier templates.
 
## Evaluation
 
`eval.py` runs every model in `eval.models` and computes:
 
- F1 per field, and separately per line-item field (`items.name`, `items.quantity`, `items.unit_price`);
- the share of replies that passed validation on the first attempt and after retries;
- the share of invented values in fields that are absent from the document;
- cost per 1000 documents, retries included;
- median and p95 latency per document.
Names are compared with a tolerance of one edit, because the generator inserts single-character typos. Invoice number and date are compared strictly, amounts with a tolerance of 0.01. Line items are matched regardless of order. If validation fails after all attempts, every field of that document counts as missed, and the document stays in the sample.
 
Results go to `results/metrics.md`, `results/eval_<time>.json` and `results/details_<time>.jsonl`. Every model call is logged to `results/calls.jsonl` with tokens, time, `doc_id` and attempt number.
 
**There are no numbers yet.** The pipeline has not been run with a real model. Cost appears only after `price_per_1m_input` and `price_per_1m_output` are set in `config.yaml`.
 
## Configuration
 
Parameters live in `config.yaml`: set size and seed, probability of missing VAT and of typos, timeouts, retries, comparison tolerances. Environment variables override the file:
 
| Variable | Purpose |
|---|---|
| `LLM_API_BASE`, `LLM_API_KEY` | LLM provider |
| `LLM_MODEL_SMALL`, `LLM_MODEL_LARGE` | Names of the small and large model |
| `INV_CONFIG` | Path to another config file |
 
The `json_mode` option in a model's config enables `response_format: json_object` for providers that support it.
 
## Layout
 
```
generate_data.py   synthetic set: gold JSON and invoice text
extract.py         one invoice: file or stdin, JSON output
eval.py            metrics for two models
invoices/          schema, normalization, pipeline, LLM client, metrics, report
tests/             168 tests, no models or network required
docs/DESIGN.md     decisions, rejected alternatives, known failure modes (in Ukrainian)
```
 
## Known limitations
 
- A single comma and a single dot in an amount are both read as decimal separators: "1,234" gives 1.234, not 1234.
- The invented-value metric covers only VAT, because that is the only field the generator can hide.
- `vat = 0` and `vat = null` are different states: a model that returns 0 instead of `null` is penalized.
- Greedy line-item matching can confuse two similar names that are within the tolerance.
- The templates contain no OCR noise, no tables split across pages and no mixed languages in item names.
