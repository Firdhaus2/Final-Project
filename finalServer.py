"""
finalServer.py
=========
OpenRefine Reconciliation Service — Singapore Street Address Matcher
W3C Reconciliation API v0.2

Run:
    pip install flask python-Levenshtein
    python finalServer.py

Then in OpenRefine:
    Reconcile -> Start reconciling -> Add Standard Service
    URL: http://localhost:5000/reconcile or the server ip that shows when you have typed the command "python finalServer.py" previously

How it works
------------
1. OpenRefine sends a raw query string (e.g. "Blk 10 Maple Rd., S'pore")
2. regex_cleaner strips noise  -> "10 Maple Rd"
3. The cleaned string is uppercased for case-insensitive comparison
4. Levenshtein distance scores it against every address in the CSV
5. Candidates above the threshold are returned, ranked best-first

Abbreviations are NOT expanded on the query side. The reference dataset
is the authority where if "MAPLE ROAD" is in the CSV, a query of "Maple Rd"
will score highly against it purely through Levenshtein distance, without
any hardcoded rule deciding that "Rd" means "Road". This avoids the
ambiguity problem where "ST" could mean either "Street" or "Saint".

The reference dataset is uppercased on load so both sides of every
comparison are in the same case.
"""

import csv
import json
import logging
import os
import re

from flask import Flask, request, jsonify, Response
from Levenshtein import distance as lev_distance

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("recon")


# CORS + logging hooks
# OpenRefine's browser-based UI treats localhost:5000 as a different origin
# Without these headers it silently rejects the response and reports
# "error : error" even when the server is responding correctly

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


#Service metadata
#Returned on a plain GET with no queries param -- OpenRefine fetches this
#first to validate and identify the service before sending any data

SERVICE_METADATA = {
    "name": "Singapore Street Address Reconciliation",
    "identifierSpace": "http://example.org/sg-streets/ids",
    "schemaSpace": "http://example.org/sg-streets/schema",
    "versions": ["0.2"],
    "batchSize": 10,
    "defaultTypes": [
        {"id": "/street/address", "name": "Singapore Street Address"}
    ],
    "view": {
        "url": "http://example.org/sg-streets/view/{{id}}"
    },
}


#Regex cleaner
#Strips noise characters from raw input before comparison
#It does NOT expand abbreviations

def _remove_country_region_suffix(text):
    """Strip ', Singapore' / ', SG' / ', S'pore' style suffixes."""
    ROAD_TYPES = (
        r"road|street|avenue|drive|lane|court|boulevard|highway|"
        r"place|terrace|crescent|square|parkway|rd|st|ave|dr|ln|"
        r"ct|blvd|hwy|pl|ter|cres|sq|pkwy|jalan|lorong|taman"
    )
    def _keep_if_road(m):
        suffix = m.group(1)
        if re.search(ROAD_TYPES, suffix, re.IGNORECASE):
            return m.group(0)
        if re.match(r"^\s*\d", suffix):
            return m.group(0)
        return ""
    return re.sub(r",(.*?)$", _keep_if_road, text)


def _remove_unit_suffix(text):
    """Strip unit/apt/floor suffixes: '123 Maple Rd - Unit 4' -> '123 Maple Rd'."""
    return re.compile(
        r"[\s,\-–—]+(?:unit|apt|apartment|suite|ste|floor|fl|#|no\.?|lot)\b.*$",
        re.IGNORECASE,
    ).sub("", text)


def _remove_block_prefix(text):
    """Strip Singapore block prefixes: 'Blk 10 ...' -> '10 ...'."""
    return re.sub(
        r"^\s*(?:(?:blk|block|hdb)(?![a-z])\.?\s*|no\.?\s*(?=\d))",
        "",
        text,
        flags=re.IGNORECASE,
    )


def clean(text):
    """
    Full noise-stripping pipeline. Returns cleaned text, uppercased,
    with whitespace normalized. Does not expand abbreviations.
    """
    if not text:
        return ""
    text = _remove_country_region_suffix(text)
    text = _remove_unit_suffix(text)
    text = _remove_block_prefix(text)
    text = re.sub(r"[#@*/\\|~^=+<>]", "", text)   # special symbols
    text = re.sub(r"[.,;:\"'()\[\]{}]", "", text)  # punctuation
    text = text.upper().strip()
    text = re.sub(r"\s+", " ", text)
    return text


#Load reference dataset
#Loaded once at startup. Addresses are uppercased so comparison is
#always case-insensitive without touching the raw form we return to users

def load_csv(filepath):
    """
    Load a CSV with 'id' and 'address' columns.
    Returns a list of dicts:
        [{"id": "1", "raw": "Maple Road", "normalized": "MAPLE ROAD"}, ...]

    The 'normalized' field is what we compare against -- uppercased and
    noise-stripped, but abbreviations are preserved exactly as they appear
    in the source data. If your CSV contains "MAPLE ROAD", queries of
    "Maple Rd" will match through Levenshtein similarity.
    """
    records = []
    with open(filepath, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = row["address"].strip()
            records.append({
                "id":         row["id"].strip(),
                "raw":        raw,
                "normalized": clean(raw),
            })
    return records


#Levenshtein scorer
#Compares the cleaned query against every record in the dataset
#Returns ranked candidates above the score threshold

def _score(a, b):
    """0-100 similarity score. 100 = identical, 0 = nothing in common."""
    if not a and not b:
        return 100.0
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 100.0
    return round((1 - lev_distance(a, b) / max_len) * 100, 1)


def find_matches(query_cleaned, records, threshold=60.0, limit=5):
    """
    Score every record against the cleaned query string and return the
    top results above the threshold, sorted best-first.

    Parameters
    ----------
    query_cleaned : output of clean() on the raw query
    records       : list from load_csv()
    threshold     : minimum score to include (0-100, defaulted to 60)
    limit         : maximum number of results to return (defaulted to 5)

    Returns
    -------
    List of result dicts in the OpenRefine reconciliation result shape:
        [{"id": ..., "name": ..., "score": ..., "match": ...}, ...]
    """
    scored = []
    for rec in records:
        score = _score(query_cleaned, rec["normalized"])
        if score >= threshold:
            scored.append({
                "id":    rec["id"],
                "name":  rec["raw"],
                "type":  [{"id": "/street/address",
                           "name": "Singapore Street Address"}],
                "score": score,
                "match": score == 100.0,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


#Startup: load the CSV once

CSV_PATH         = "reference_dataset.csv"
SUGGESTIONS_PATH = "suggested_addresses.csv"

try:
    ADDRESS_RECORDS = load_csv(CSV_PATH)
    log.info("Loaded %d addresses from %s", len(ADDRESS_RECORDS), CSV_PATH)
except FileNotFoundError:
    log.error("CSV not found: %s — server will start but return no results", CSV_PATH)
    ADDRESS_RECORDS = []

#Flask routes

def _jsonp_or_json(payload):
    """Return JSON, or JSONP-wrapped if OpenRefine sent a callback param."""
    callback = request.args.get("callback")
    if callback:
        return Response(
            f"{callback}({json.dumps(payload)});",
            mimetype="application/javascript"
        )
    return jsonify(payload)


@app.route("/reconcile", methods=["GET", "POST", "OPTIONS"])
def reconcile():
    # CORS preflight
    if request.method == "OPTIONS":
        return Response(status=204)

    # Extract the queries param -- OpenRefine sends it in different ways
    # depending on the version: form-encoded, query string, or JSON body
    queries_raw = request.form.get("queries") or request.args.get("queries")

    if not queries_raw and request.is_json:
        body = request.get_json(silent=True) or {}
        queries_raw = body.get("queries")
        if isinstance(queries_raw, dict):
            return _process_queries(queries_raw)

    # No queries param -> metadata discovery request
    if not queries_raw:
        return _jsonp_or_json(SERVICE_METADATA)

    try:
        queries = json.loads(queries_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid 'queries' JSON"}), 400

    return _process_queries(queries)


def _process_queries(queries):
    """
    Core reconciliation handler.

    For each query:
      1. clean()        -- strip noise, uppercase
      2. find_matches() -- Levenshtein score against CSV records
      3. Package results in the OpenRefine result shape
    """
    results = {}
    for query_id, query in queries.items():
        query_text = query.get("query")
        limit = query.get("limit", 5)

        # Spec allows queries without a 'query' field (properties-only)
        # We only support text matching so return empty for those
        if not query_text or limit == 0:
            results[query_id] = {"result": []}
            continue

        cleaned = clean(query_text)
        log.info("Query [%s]: %r -> cleaned: %r", query_id, query_text, cleaned)

        matches = find_matches(cleaned, ADDRESS_RECORDS, threshold=60.0, limit=limit)
        results[query_id] = {"result": matches}

        if not matches or matches[0]["score"] < 75:
            _save_suggestion(query_text, cleaned)

    return _jsonp_or_json(results)


def _save_suggestion(raw_text, cleaned):
    try:
        existing = set()
        try:
            with open(SUGGESTIONS_PATH, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    existing.add(row["address"].strip().upper())
        except FileNotFoundError:
            pass

        if cleaned in existing:
            return

        file_is_new = not os.path.exists(SUGGESTIONS_PATH)
        with open(SUGGESTIONS_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if file_is_new:
                writer.writerow(["address"])
            writer.writerow([raw_text])

        log.info("Low confidence — saved suggestion: %r", cleaned)

    except Exception as e:
        log.warning("Could not save suggestion %r: %s", cleaned, e)

@app.route("/", methods=["GET"])
def root():
    return _jsonp_or_json(SERVICE_METADATA)


@app.route("/search", methods=["GET"])
def search():
    """
    Helper endpoint for manual testing -- not part of the reconciliation
    protocol. Allows to test a query directly in the browser:

        http://localhost:5000/search?q=Blk+12+Maple+Rd
        In my case it is:
        http://192.168.0.225:5000/search?q=Sunset+Dr
    """
    raw = request.args.get("q", "")
    cleaned = clean(raw)
    matches = find_matches(cleaned, ADDRESS_RECORDS, threshold=60.0, limit=5)
    return jsonify({
        "raw":     raw,
        "cleaned": cleaned,
        "results": matches,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
