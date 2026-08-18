"""
OpenRefine Reconciliation Service - Street Name Normalizer
=============================================================

Implements the OpenRefine Reconciliation API (v0.2) so it can be added
as a custom reconciliation service inside OpenRefine:

    Refine menu -> Reconcile -> Start reconciling -> Add Standard Service
    URL: http://localhost:5000/reconcile

What it does
------------
Rather than matching against a fixed list of "real" entities, this service
takes the street string OpenRefine sends, normalizes abbreviations
(RD -> ROAD, ST -> STREET, AVE -> AVENUE, etc.), and returns the
normalized form as a single high-confidence match. This lets you use
OpenRefine's reconciliation UI (and "Add column from reconciled values")
to bulk-clean a street name column.

Run:
    python server.py
Then in OpenRefine, point a column's reconciliation at:
    http://localhost:5000/reconcile
"""

import re
import logging
from flask import Flask, request, jsonify, Response
import json

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("recon")


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.before_request
def log_request():
    log.info(
        "Incoming %s %s | args=%s form=%s",
        request.method, request.path, dict(request.args), dict(request.form)
    )


def jsonp_or_json(payload):
    """
    Return plain JSON normally, or wrap in a JS callback if OpenRefine
    requested JSONP (via a `callback` query param) for CORS-fallback mode.
    """
    callback = request.args.get("callback")
    if callback:
        body = f"{callback}({json.dumps(payload)});"
        return Response(body, mimetype="application/javascript")
    return jsonify(payload)


#Core normalization logic

#Hardcoded text to change 
REPLACEMENTS_ANYWHERE = [
    (r"\bRD\b", "ROAD"),
    (r"\bST\b", "STREET"),
    (r"\bAVE\b", "AVENUE"),
    (r"\bDR\b", "DRIVE"),
    (r"\bLN\b", "LANE"),
    (r"\bCT\b", "COURT"),
    (r"\bBLVD\b", "BOULEVARD"),
    (r"\bHWY\b", "HIGHWAY"),
    (r"\bPL\b", "PLACE"),
    (r"\bTER\b", "TERRACE"),
    (r"\bCRES\b", "CRESCENT"),
    (r"\bSQ\b", "SQUARE"),
    (r"\bPKWY\b", "PARKWAY"),
    (r"\bJLN\b", "JALAN"),
    (r"\bGDNS\b", "GARDENS"),
    (r"\bSTH\b", "SOUTH"),
]


def normalize_street(text):
    """
    Normalize street-name abbreviations to their full word form.

    Example: "Mandai St" to "MANDAI STREET"
             "45 Oak Rd" to "45 OAK ROAD"
    """
    if not text:
        return ""

    text = text.upper().strip()
    # Collapse any irregular whitespace first so word-boundary regex behaves
    text = re.sub(r"\s+", " ", text)

    for pattern, full in REPLACEMENTS_ANYWHERE:
        text = re.sub(pattern, full, text)

    # Re-collapse whitespace in case a replacement introduced double spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Reconciliation service metadata
# This is what OpenRefine fetches via GET to identify/validate the service.
# ---------------------------------------------------------------------------
#
SERVICE_METADATA = {
    "name": "Street Name Normalizer",
    "identifierSpace": "http://example.org/streetnormalizer/ids",
    "schemaSpace": "http://example.org/streetnormalizer/schema",
    "versions": ["0.2"],
    "batchSize": 10,
    "defaultTypes": [
        {"id": "/street/address", "name": "Normalized Street Address"}
    ],
    "view": {
        # {{id}} is substituted by OpenRefine if a user clicks through a match
        "url": "http://example.org/streetnormalizer/view/{{id}}"
    },
}


def build_match(original_text):
    """
    Build a single reconciliation candidate: the normalized string.
    Score is always 100 and match=True since this is a deterministic
    transform, not a fuzzy lookup against a real entity database.
    """
    normalized = normalize_street(original_text)
    return {
        "id": normalized,        # we use the normalized string itself as the "id"
        "name": normalized,
        "type": [{"id": "/street/address", "name": "Normalized Street Address"}],
        "score": 100,
        "match": True,
    }

# Routes

@app.route("/reconcile", methods=["GET", "POST", "OPTIONS"])
def reconcile():
    if request.method == "OPTIONS":
        return Response(status=204)

    queries_raw = request.form.get("queries") or request.args.get("queries")

    if not queries_raw and request.is_json:
        body = request.get_json(silent=True) or {}
        queries_raw = body.get("queries")
        if isinstance(queries_raw, dict):
            # already parsed JSON object, not a string
            queries = queries_raw
            return _do_reconcile(queries)

    if not queries_raw:
        # No queries param at all -> this is a metadata discovery request
        return jsonp_or_json(SERVICE_METADATA)

    try:
        queries = json.loads(queries_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid 'queries' JSON"}), 400

    return _do_reconcile(queries)


def _do_reconcile(queries):
    results = {}
    for query_id, query in queries.items():
        query_text = query.get("query")
        limit = query.get("limit", 1)

        # Spec allows a query to omit "query" if it supplies "properties"
        # instead. We only match on query text, so anything without it
        # (or an explicit limit=0) correctly gets zero candidates back.
        if not query_text or limit == 0:
            results[query_id] = {"result": []}
            continue

        results[query_id] = {"result": [build_match(query_text)]}
    return jsonp_or_json(results)


@app.route("/", methods=["GET"])
def root():
    # Some OpenRefine versions probe the root URL too; just mirror metadata.
    return jsonp_or_json(SERVICE_METADATA)


@app.route("/normalize", methods=["GET"])
def normalize_endpoint():
    """
    Plain helper endpoint (NOT part of the reconciliation protocol)
    to quickly sanity-check normalization in a browser or with curl:

        curl "http://localhost:5000/normalize?text=123+Main+Rd"
    """
    text = request.args.get("text", "")
    return jsonify({"input": text, "normalized": normalize_street(text)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
