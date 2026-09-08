import copy
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from mcp_native_metrics import METRICS, RenderMetrics, render_metrics


def payload(timestamp, **values):
    values = {"enabled": 2, "kept": 2, "omitted": 0, "truncated_chars": 0, **values}
    return {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.version", "value": {"stringValue": "0.153.4"}},
                        {"key": "private", "value": {"stringValue": "private-account"}},
                    ]
                },
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": name,
                                "histogram": {
                                    "dataPoints": [
                                        {
                                            "attributes": [
                                                {"key": "catalog_surface", "value": {"stringValue": "thread_context"}}
                                            ],
                                            "count": "1",
                                            "timeUnixNano": str(timestamp),
                                            "min": values[key],
                                            "max": values[key],
                                            "sum": values[key],
                                        }
                                    ]
                                },
                            }
                            for name, key in METRICS.items()
                        ]
                    }
                ],
            }
        ]
    }


def test_native_zero_metrics_are_positive_evidence():
    assert render_metrics(payload(10), "0.153.4", 10) == {"enabled": 2, "kept": 2, "omitted": 0, "truncated_chars": 0}


@pytest.mark.parametrize(
    "defect", ["old", "version", "missing", "mixed", "varying", "duplicate", "wrong_surface", "nan", "empty_count"]
)
def test_incomplete_or_ambiguous_metrics_cannot_certify_rendering(defect):
    value = payload(10)
    metrics = value["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    point = metrics[0]["histogram"]["dataPoints"][0]
    version, started = "0.153.4", 10
    if defect == "old":
        started = 11
    elif defect == "version":
        version = "next"
    elif defect == "missing":
        metrics.pop()
    elif defect == "mixed":
        point["timeUnixNano"] = "2000000011"
    elif defect == "varying":
        point["max"] = 4
    elif defect == "duplicate":
        metrics.append(copy.deepcopy(metrics[0]))
    elif defect == "wrong_surface":
        point["attributes"][0]["value"]["stringValue"] = "host_world_state"
    elif defect == "nan":
        point["sum"] = float("nan")
    else:
        point["count"] = "0"
    assert render_metrics(value, version, started) is None


def test_loopback_receiver_requires_ephemeral_capability_and_drops_private_data():
    receiver = RenderMetrics("0.153.4")
    receiver.start()
    url = f"http://127.0.0.1:{receiver.server.server_address[1]}/v1/metrics"
    body = json.dumps(payload(time.time_ns())).encode()
    try:
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=2)
        assert denied.value.code == 403
        request = urllib.request.Request(
            url, data=body, headers={"Authorization": "Bearer " + receiver.token, "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            assert response.status == 200
        evidence = receiver.evidence(2)
        assert evidence["state"] == "pass"
        assert "private-account" not in json.dumps(evidence)
        assert receiver.evidence(3)["state"] == "unmeasured"
        assert receiver.evidence(0)["state"] == "unmeasured"
    finally:
        receiver.close()
    assert not receiver.thread.is_alive()


def test_observed_native_truncation_is_failure_not_missing_data():
    receiver = RenderMetrics("0.153.4")
    try:
        receiver.latest = render_metrics(payload(10, kept=1, omitted=1, truncated_chars=200), "0.153.4", 10)
        assert receiver.evidence(2, timeout=0)["state"] == "fail"
    finally:
        receiver.close()
