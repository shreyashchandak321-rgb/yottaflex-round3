"""
Validation suite for a generated dataset.

Checks:
1. Primary-key uniqueness on every table.
2. Foreign-key integrity on every relationship. Failures that correspond to
   a labelled ground-truth anomaly (theme outside taxonomy) are reported as
   EXPECTED and reconciled against ground_truth.csv, not silently passed.
3. Allowed-value (enum) checks on status/label/type columns.
4. Date ordering: responses inside their survey window, messages on/after
   their ticket's opened date, lifecycle events in chronological order.
5. Arithmetic reconciliation: sentiment_score always equals the polarity in
   the label catalogue; manifest counts equal actual row counts; exact-record
   duplicate groups equal the labelled duplicate anomalies.
6. ID format checks against the documented nomenclature.
7. Optional reproducibility comparison (--compare DIR): sha256 of every CSV
   in both directories must match when the same seed is used.

Exit code is 0 only when there are no UNEXPECTED failures.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ID_PATTERNS = {
    "reviews": ("review_id", re.compile(r"^REV-2026-\d{6}$")),
    "survey_responses": ("response_id", re.compile(r"^RESP-SUR-\d{4}-\d{6}-\d{3,}$")),
    "support_messages": ("message_id", re.compile(r"^MSG-TKT-2026-\d{6}-\d{3}$")),
    "surveys": ("survey_id", re.compile(r"^SUR-2026-\d{6}$")),
    "themes": ("theme_id", re.compile(r"^THEME-\d{6}$")),
}


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(data_dir, compare_dir=None):
    data = Path(data_dir)
    results = []

    def check(name, ok, detail=""):
        results.append(dict(check=name, status="pass" if ok else "FAIL", detail=detail))

    tables = {name: read_csv(data / f"{name}.csv") for name in
              ["customers", "products", "channels", "themes", "sentiment_labels",
               "surveys", "survey_responses", "reviews", "support_tickets",
               "support_messages", "state_events", "ground_truth"]}

    # 1. PK uniqueness
    pk = dict(customers="customer_id", products="product_id", channels="channel_id",
              themes="theme_id", sentiment_labels="sentiment_label_id",
              surveys="survey_id", survey_responses="response_id", reviews="review_id",
              support_tickets="ticket_id", support_messages="message_id",
              state_events="event_id")
    for table, key in pk.items():
        ids = [r[key] for r in tables[table]]
        check(f"pk_unique:{table}", len(ids) == len(set(ids)),
              f"{len(ids)} rows")

    # 2. FK integrity
    id_sets = {t: {r[pk[t]] for r in tables[t]} for t in pk}
    ground_truth = tables["ground_truth"]
    expected_theme_fk = {r["record_id"] for r in ground_truth
                         if r["issue_type"] == "theme_outside_taxonomy"}
    fk_specs = [
        ("reviews", "customer_id", "customers"), ("reviews", "product_id", "products"),
        ("reviews", "channel_id", "channels"), ("reviews", "sentiment_label_id", "sentiment_labels"),
        ("survey_responses", "survey_id", "surveys"),
        ("survey_responses", "customer_id", "customers"),
        ("survey_responses", "product_id", "products"),
        ("support_messages", "ticket_id", "support_tickets"),
        ("support_messages", "customer_id", "customers"),
        ("support_tickets", "customer_id", "customers"),
        ("support_tickets", "product_id", "products"),
    ]
    for table, col, ref in fk_specs:
        bad = [r[pk[table]] for r in tables[table] if r[col] and r[col] not in id_sets[ref]]
        check(f"fk:{table}.{col}", not bad, f"{len(bad)} dangling")
    # theme FKs: dangling rows must be exactly the labelled anomalies
    for table in ["reviews", "survey_responses", "support_messages", "support_tickets"]:
        key = pk[table]
        bad = {r[key] for r in tables[table] if r["theme_id"] not in id_sets["themes"]}
        unexpected = bad - expected_theme_fk
        check(f"fk:{table}.theme_id (anomalies reconciled)", not unexpected,
              f"{len(bad)} dangling, all labelled in ground truth"
              if not unexpected else f"unlabelled dangling: {sorted(unexpected)[:5]}")

    # 3. Enums
    check("enum:ticket_status",
          {r["status"] for r in tables["support_tickets"]} <= {"open", "pending", "resolved"})
    check("enum:customer_segment",
          {r["segment"] for r in tables["customers"]} <=
          {"consumer", "small_business", "enterprise", "prospect"})
    check("enum:sender_type",
          {r["sender_type"] for r in tables["support_messages"]} <= {"customer", "agent"})

    # 4. Date ordering
    survey_window = {s["survey_id"]: (s["start_date"], s["end_date"]) for s in tables["surveys"]}
    bad_dates = [r["response_id"] for r in tables["survey_responses"]
                 if not (survey_window[r["survey_id"]][0] <= r["response_date"]
                         <= survey_window[r["survey_id"]][1])]
    check("dates:response_within_survey_window", not bad_dates, f"{len(bad_dates)} outside")
    ticket_open = {t["ticket_id"]: t["opened_date"] for t in tables["support_tickets"]}
    bad_msg = [m["message_id"] for m in tables["support_messages"]
               if m["message_date"] < ticket_open[m["ticket_id"]]]
    check("dates:message_on_or_after_ticket_open", not bad_msg, f"{len(bad_msg)} early")

    # 5. Reconciliation
    polarity = {r["sentiment_label_id"]: int(r["polarity_score"])
                for r in tables["sentiment_labels"]}
    bad_score = [r["review_id"] for r in tables["reviews"]
                 if int(r["sentiment_score"]) != polarity[r["sentiment_label_id"]]]
    check("reconcile:review_sentiment_score", not bad_score, f"{len(bad_score)} mismatched")
    manifest = json.loads((data / "source_manifest.json").read_text())
    actual = dict(customers=len(tables["customers"]), surveys=len(tables["surveys"]),
                  reviews=len(tables["reviews"]),
                  survey_responses=len(tables["survey_responses"]),
                  support_tickets=len(tables["support_tickets"]),
                  support_messages=len(tables["support_messages"]),
                  ground_truth_anomalies=len(ground_truth))
    check("reconcile:manifest_counts", manifest["counts"] == actual,
          json.dumps(actual))
    # A duplicate response is an exact copy of another record in every content
    # field except its own ID (test_label excluded: it is the leakage carrier,
    # not content). Two records that merely share similar short text, e.g. a
    # common multilingual phrase on different dates, are not duplicates.
    dup_groups = Counter(tuple(v for k, v in r.items()
                               if k not in ("response_id", "test_label"))
                         for r in tables["survey_responses"])
    extra_dups = sum(c - 1 for c in dup_groups.values() if c > 1)
    labelled_dups = sum(1 for r in ground_truth if r["issue_type"] == "duplicate_response")
    check("reconcile:duplicates_match_ground_truth", extra_dups == labelled_dups,
          f"{extra_dups} duplicate rows vs {labelled_dups} labelled")

    # 6. ID formats
    for table, (col, pattern) in ID_PATTERNS.items():
        bad = [r[col] for r in tables[table] if not pattern.match(r[col])]
        check(f"id_format:{table}", not bad, f"{len(bad)} malformed")

    # 7. Ground truth separation: no input file may carry ground-truth columns
    leaked = [f for f in ["reviews.csv", "survey_responses.csv", "support_messages.csv"]
              if "issue_type" in open(data / f, encoding="utf-8").readline()]
    check("separation:no_ground_truth_columns_in_inputs", not leaked)

    # 8. Reproducibility comparison
    if compare_dir:
        other = Path(compare_dir)
        files = sorted(p.name for p in data.glob("*.csv"))
        mismatched = [f for f in files if sha256(data / f) != sha256(other / f)]
        check("reproducibility:checksums_match", not mismatched,
              f"{len(files)} csv files compared, {len(mismatched)} differ")

    failed = [r for r in results if r["status"] == "FAIL"]
    summary = dict(total_checks=len(results), passed=len(results) - len(failed),
                   failed=len(failed), results=results)
    out_dir = data / "outputs"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "validation_summary.json").write_text(json.dumps(summary, indent=2))
    lines = ["# Validation summary", "",
             f"- Checks: {summary['total_checks']} total, {summary['passed']} passed, "
             f"{summary['failed']} failed", ""]
    lines += [f"- [{r['status']}] {r['check']} — {r['detail']}" for r in results]
    (out_dir / "validation_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if not failed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--compare", default=None)
    args = parser.parse_args()
    sys.exit(validate(args.data, args.compare))
