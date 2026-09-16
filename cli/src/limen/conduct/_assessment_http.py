"""Private isolated-process HTTP primitive for the assessment client.

Run by absolute installed path with Python -I. All authority arrives over stdin;
no ambient credentials, proxy configuration or redirect target is consulted.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

LIMIT = 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def exchange(request):
    url = urllib.parse.urlsplit(request["url"])
    if (
        url.username is not None
        or url.password is not None
        or url.fragment
        or not url.hostname
        or not (url.scheme == "https" or (url.scheme == "http" and url.hostname == "127.0.0.1" and url.port))
        or request["method"] not in {"GET", "POST"}
    ):
        raise ValueError
    body = request["payload"]
    encoded = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    headers = {
        "Authorization": "Bearer " + request["credential"],
        "Accept": "application/json",
        "User-Agent": "limen-assessment-client/1",
    }
    if encoded is not None:
        headers["Content-Type"] = "application/json"
    outgoing = urllib.request.Request(request["url"], data=encoded, method=request["method"], headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(outgoing, timeout=15) as response:
            status = response.status
            raw = response.read(LIMIT + 1)
    except urllib.error.HTTPError as error:
        # Never echo provider error bodies; they can contain credential material.
        return {"status": error.code}
    if len(raw) > LIMIT:
        raise ValueError
    payload = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(payload, dict):
        raise ValueError
    return {"status": status, "payload": payload}


def main():
    try:
        raw = sys.stdin.buffer.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError
        result = exchange(json.loads(raw))
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return 77


if __name__ == "__main__":
    raise SystemExit(main())
