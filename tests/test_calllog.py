import json

from invoices.calllog import CallLog


def test_summary_and_cost():
    log = CallLog(price_per_1m_input=2.0, price_per_1m_output=4.0)
    log.record(model="m", input_tokens=1000, output_tokens=500, latency_s=1.0)
    log.record(model="m", input_tokens=1000, output_tokens=500, latency_s=3.0)
    summary = log.summary()
    assert summary["calls"] == 2
    assert summary["input_tokens"] == 2000 and summary["output_tokens"] == 1000
    assert summary["latency_p50_s"] == 1.0 and summary["latency_p95_s"] == 3.0
    assert summary["cost"] == (2000 / 1e6 * 2.0) + (1000 / 1e6 * 4.0)


def test_cost_none_without_prices():
    log = CallLog()
    log.record(model="m", input_tokens=10, output_tokens=10, latency_s=0.1)
    assert log.summary()["cost"] is None


def test_failed_call_breaks_cost():
    log = CallLog(price_per_1m_input=1.0, price_per_1m_output=1.0)
    log.record(model="m", input_tokens=10, output_tokens=10, latency_s=0.1)
    log.record(model="m", input_tokens=None, output_tokens=None, latency_s=0.2,
               ok=False, error="http 429")
    summary = log.summary()
    assert summary["failed"] == 1
    assert summary["cost"] is None


def test_empty_log():
    summary = CallLog().summary()
    assert summary["calls"] == 0 and summary["cost"] is None
    assert summary["latency_p50_s"] is None


def test_records_append_with_extra(tmp_path):
    path = tmp_path / "nested" / "calls.jsonl"
    log = CallLog(path)
    log.record(model="m", input_tokens=1, output_tokens=2, latency_s=0.1,
               extra={"doc_id": "inv-0001", "attempt": 2})
    log.record(model="m", input_tokens=3, output_tokens=4, latency_s=0.2)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["doc_id"] == "inv-0001" and rows[0]["attempt"] == 2
