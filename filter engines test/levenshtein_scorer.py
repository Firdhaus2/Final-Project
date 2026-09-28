"""
score_curve_test.py
====================
Simple, self-contained test for the Levenshtein scorer.

Takes one base address and compares it against a series of variants,
printing the edit distance and 0-100 score for each -- so you can see
the score drop as the variants get further from the original.

Run:
    pip install python-Levenshtein
    python score_curve_test.py
"""

from Levenshtein import distance as lev_distance


def levenshtein_score(a, b):
    """0-100 similarity score. 100 = identical, 0 = nothing in common."""
    if not a and not b:
        return 100.0
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 100.0
    return round((1 - lev_distance(a, b) / max_len) * 100, 1)


if __name__ == "__main__":
    base = "123 MAPLE ROAD"

    candidates = [
        "123 MAPLE ROAD",
        "123 MAPLE ROAR",
        "123 MAPLE ROA",
        "123 MAPLE RO",
        "123 MAPEL ROAD",
        "124 MAPLE ROAD",
        "123 OAK ROAD",
        "456 PINE STREET",
    ]

    print("--- Score curve: ---")
    print(f"{'Query':<25} {'Candidate':<25} {'Dist':>5} {'Score':>6}")
    print("-" * 65)

    for candidate in candidates:
        dist = lev_distance(base, candidate)
        score = levenshtein_score(base, candidate)
        print(f"{base:<25} {candidate:<25} {dist:>5} {score:>6}")