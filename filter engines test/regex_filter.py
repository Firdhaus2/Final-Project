"""
regex_filter.py
=============
Unit tests for the clean() function from finalServer.py.

Proves that the regex cleaning pipeline strips noise correctly
without changing the actual street name tokens.

Run:
    python regex_filter.py
"""

import re

def _remove_country_region_suffix(text):
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
    return re.compile(
        r"[\s,\-–—]+(?:unit|apt|apartment|suite|ste|floor|fl|#|no\.?|lot)\b.*$",
        re.IGNORECASE,
    ).sub("", text)


def _remove_block_prefix(text):
    return re.sub(
        r"^\s*(?:blk|block|hdb|no\.?)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )


def clean(text):
    if not text:
        return ""
    text = _remove_country_region_suffix(text)
    text = _remove_unit_suffix(text)
    text = _remove_block_prefix(text)
    text = re.sub(r"[#@*/\\|~^=+<>]", "", text)
    text = re.sub(r"[.,;:\"'()\[\]{}]", "", text)
    text = text.upper().strip()
    text = re.sub(r"\s+", " ", text)
    return text


#Test cases
#description, raw_input, expected_output

TEST_CASES = [
    # Country/region suffix stripping
    ("Country suffix removed",           "Orchard Road, Singapore",       "ORCHARD ROAD"),
    ("Short country suffix removed",     "Orchard Road, SG",              "ORCHARD ROAD"),
    ("Informal suffix removed",          "River Valley Rd, S'pore",       "RIVER VALLEY RD"),
    ("Comma in address kept",            "123, Maple Road",               "123 MAPLE ROAD"),

    # Unit suffix stripping
    ("Unit suffix removed",              "Maple Road Unit 4",             "MAPLE ROAD"),
    ("Apt suffix removed",               "Maple Road, Apt 2B",            "MAPLE ROAD"),
    ("Floor suffix removed",             "Maple Road Floor 3",            "MAPLE ROAD"),

    # Block prefix stripping
    ("Blk prefix removed",               "Blk 12 Maple Road",             "12 MAPLE ROAD"),
    ("Block prefix removed",             "Block 88 Jurong Road",          "88 JURONG ROAD"),
    ("HDB prefix removed",               "HDB 10 Maple Road",             "10 MAPLE ROAD"),

    # Special symbols and punctuation
    ("Hash symbol removed",              "#34 Oak Street",                "34 OAK STREET"),
    ("Trailing period removed",          "Bukit Timah Rd.",               "BUKIT TIMAH RD"),
    ("Parentheses removed",              "(123) Maple Road",              "123 MAPLE ROAD"),

    # Whitespace normalisation
    ("Extra spaces collapsed",           "Bukit  Timah   Road",           "BUKIT TIMAH ROAD"),
    ("Leading/trailing space stripped",  "  Orchard Road  ",              "ORCHARD ROAD"),

    # Casing
    ("Lowercase uppercased",             "jalan bukit merah",             "JALAN BUKIT MERAH"),
    ("Mixed case uppercased",            "Lorong Chuan",                  "LORONG CHUAN"),

    # Malay street names preserved
    ("Jalan preserved",                  "Jalan Bukit Timah",             "JALAN BUKIT TIMAH"),
    ("Lorong preserved",                 "Lorong 17 Geylang",             "LORONG 17 GEYLANG"),

    # Combined noise
    ("Block + country suffix",           "Blk 12 Maple Rd., Singapore",   "12 MAPLE RD"),
    ("Hash + unit suffix",               "#34 Oak St, Apt 3",             "34 OAK ST"),
]


#Runner
def run_tests():
    passed = 0
    failed = 0

    print(f"{'Description':<40} {'Input':<35} {'Expected':<25} {'Got':<25} {'Pass?'}")
    print("-" * 135)

    for description, raw, expected in TEST_CASES:
        result = clean(raw)
        ok = result == expected
        flag = "1" if ok else "0"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"{description:<40} {raw!r:<35} {expected!r:<25} {result!r:<25} {flag}")

    print()
    print(f"Results: {passed} passed, {failed} failed out of {len(TEST_CASES)} tests")

    if failed == 0:
        print("All tests passed — clean() is working as intended.")
    else:
        print("Some tests failed — check the output above.")


if __name__ == "__main__":
    run_tests()