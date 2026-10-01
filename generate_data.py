"""
Generates the synthetic incident dataset used by the agent demo.

Design notes (these matter more than the code):

1. The data is SEEDED. Same input, same database, every time. A demo you
   cannot reproduce is a demo you cannot rehearse.

2. The distribution is deliberately uneven, because real incident data is.
   Severity follows a realistic pyramid (few Sev-1s, many Sev-3s) and
   resolution times are long-tailed. If you generate uniformly, every
   aggregate the agent computes comes back boring and the demo falls flat.

3. There is a PLANTED CLUSTER: the payments service has a recurring
   connection-pool exhaustion problem across several months. This is what
   makes "has this happened before?" have a real answer. Without a planted
   pattern there is nothing for retrieval to find.

4. Contact details (name, phone) are stored in the same table as everything
   else. They are NOT separated into a "secret" table. The access boundary
   is enforced in the tool layer, not by hiding the column. That is the
   whole point of the demo.
"""

import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 20261005
random.seed(SEED)

DB_PATH = Path(__file__).parent / "data" / "incidents.db"

# Window: 12 months ending just before the presentation date.
END_DATE = datetime(2026, 9, 26)
START_DATE = END_DATE - timedelta(days=365)

# ---------------------------------------------------------------------------
# Services. Each has an owning team, an on-call contact, and a "personality"
# that shapes which failures it tends to have. Realistic data needs services
# that fail in characteristic ways, not random assignment.
# ---------------------------------------------------------------------------

SERVICES = {
    "payments": {
        "team": "Payments Platform",
        "contact": ("Dana Whitfield", "+1-415-555-0142"),
        "weight": 22,
        "causes": ["connection_pool", "downstream_timeout", "deploy_regression",
                   "rate_limit", "certificate_expiry"],
    },
    "checkout": {
        "team": "Storefront",
        "contact": ("Marcus Reyes", "+1-415-555-0178"),
        "weight": 16,
        "causes": ["downstream_timeout", "deploy_regression", "cache_stampede",
                   "memory_leak"],
    },
    "auth": {
        "team": "Identity",
        "contact": ("Priya Raghunathan", "+1-415-555-0193"),
        "weight": 14,
        "causes": ["certificate_expiry", "rate_limit", "config_drift",
                   "downstream_timeout"],
    },
    "search": {
        "team": "Discovery",
        "contact": ("Tomas Lindqvist", "+1-415-555-0107"),
        "weight": 13,
        "causes": ["index_corruption", "memory_leak", "cache_stampede",
                   "resource_exhaustion"],
    },
    "inventory": {
        "team": "Supply Systems",
        "contact": ("Aisha Bello", "+1-415-555-0164"),
        "weight": 11,
        "causes": ["replication_lag", "deploy_regression", "config_drift",
                   "connection_pool"],
    },
    "notifications": {
        "team": "Messaging",
        "contact": ("Ellis Farrow", "+1-415-555-0121"),
        "weight": 10,
        "causes": ["rate_limit", "queue_backlog", "downstream_timeout"],
    },
    "reporting": {
        "team": "Data Platform",
        "contact": ("Nadia Osei", "+1-415-555-0155"),
        "weight": 8,
        "causes": ["queue_backlog", "resource_exhaustion", "replication_lag",
                   "disk_pressure"],
    },
    "media-upload": {
        "team": "Content Infrastructure",
        "contact": ("Jonah Krantz", "+1-415-555-0189"),
        "weight": 6,
        "causes": ["disk_pressure", "memory_leak", "resource_exhaustion"],
    },
}

# Severity pyramid. Sev-1 is rare and expensive; Sev-3 is the daily grind.
SEVERITY_WEIGHTS = [("Sev-1", 7), ("Sev-2", 23), ("Sev-3", 70)]

# Resolution time ranges in minutes, by severity.
# Sev-1 gets everyone on a call fast. Sev-3 sits in a queue for hours.
DURATION_RANGES = {
    "Sev-1": (25, 240),
    "Sev-2": (40, 600),
    "Sev-3": (60, 2880),
}

# Title templates per root cause. Deliberately varied wording, because if
# every title for a cause is identical then semantic search has nothing to do.
CAUSE_TITLES = {
    "connection_pool": [
        "Elevated {svc} latency during peak traffic",
        "{svc} request queueing under sustained load",
        "Intermittent {svc} timeouts, no upstream errors",
        "{svc} p99 latency degradation",
        "Slow {svc} responses with healthy dependencies",
    ],
    "downstream_timeout": [
        "{svc} errors following dependency slowdown",
        "Cascading failures in {svc} from upstream latency",
        "{svc} 5xx spike traced to third-party API",
    ],
    "deploy_regression": [
        "{svc} error rate increase after release",
        "Regression in {svc} introduced by deployment",
        "{svc} failures following configuration rollout",
    ],
    "rate_limit": [
        "{svc} requests rejected by rate limiter",
        "Throttling applied to {svc} traffic",
        "{svc} clients receiving 429 responses",
    ],
    "certificate_expiry": [
        "{svc} TLS handshake failures",
        "Expired certificate breaking {svc} connections",
    ],
    "cache_stampede": [
        "{svc} origin overload after cache eviction",
        "Thundering herd against {svc} backend",
    ],
    "memory_leak": [
        "{svc} pods restarting under memory pressure",
        "Gradual memory growth in {svc} workers",
        "{svc} OOM kills during extended uptime",
    ],
    "index_corruption": [
        "{svc} returning incomplete results",
        "Stale index causing {svc} result gaps",
    ],
    "replication_lag": [
        "{svc} reads serving stale data",
        "Replica lag affecting {svc} consistency",
    ],
    "queue_backlog": [
        "{svc} processing delays from queue depth",
        "Backlog accumulation in {svc} consumers",
    ],
    "resource_exhaustion": [
        "{svc} CPU saturation during batch window",
        "{svc} unable to schedule additional workers",
    ],
    "config_drift": [
        "{svc} behaviour diverging between environments",
        "Misapplied configuration affecting {svc}",
    ],
    "disk_pressure": [
        "{svc} write failures from disk capacity",
        "{svc} storage threshold exceeded",
    ],
}

# ---------------------------------------------------------------------------
# The planted cluster.
#
# payments hits connection-pool exhaustion five times across the year, with
# escalating severity, because the underlying fix kept being deferred. This
# is the story the agent uncovers in the demo. The titles avoid repeating
# the exact phrase "connection pool" so that retrieval has to work
# semantically rather than by keyword match.
# ---------------------------------------------------------------------------

PLANTED_PAYMENTS_CLUSTER = [
    {
        "opened": datetime(2025, 11, 14, 9, 22),
        "severity": "Sev-3",
        "title": "Slow payments responses during morning peak",
        "duration": 156,
    },
    {
        "opened": datetime(2026, 1, 29, 14, 5),
        "severity": "Sev-2",
        "title": "Payments p99 latency degradation under load",
        "duration": 203,
    },
    {
        "opened": datetime(2026, 3, 18, 2, 47),
        "severity": "Sev-1",
        "title": "Elevated payments latency, checkout failures",
        "duration": 88,
    },
    {
        "opened": datetime(2026, 6, 3, 16, 31),
        "severity": "Sev-2",
        "title": "Intermittent payments timeouts with healthy dependencies",
        "duration": 174,
    },
    {
        "opened": datetime(2026, 8, 21, 11, 9),
        "severity": "Sev-2",
        "title": "Payments request queueing during sustained traffic",
        "duration": 142,
    },
]


def weighted_choice(pairs):
    population = [p[0] for p in pairs]
    weights = [p[1] for p in pairs]
    return random.choices(population, weights=weights, k=1)[0]


def random_timestamp():
    """Incidents cluster in business hours but never entirely. The 2am
    incident in the talk has to be plausible, so nights stay populated."""
    delta_days = random.randint(0, 364)
    day = START_DATE + timedelta(days=delta_days)
    if random.random() < 0.72:
        hour = random.randint(8, 19)      # business hours
    else:
        hour = random.choice([0, 1, 2, 3, 4, 5, 6, 7, 20, 21, 22, 23])
    return day.replace(hour=hour, minute=random.randint(0, 59), second=0,
                       microsecond=0)


def build_incidents(total=200):
    rows = []
    counter = 1

    # Planted cluster first, so it gets low, memorable IDs in date order later.
    for item in PLANTED_PAYMENTS_CLUSTER:
        cfg = SERVICES["payments"]
        rows.append({
            "service": "payments",
            "severity": item["severity"],
            "title": item["title"],
            "opened_at": item["opened"],
            "duration_minutes": item["duration"],
            "root_cause_category": "connection_pool",
            "owning_team": cfg["team"],
            "contact_name": cfg["contact"][0],
            "contact_phone": cfg["contact"][1],
        })

    service_names = list(SERVICES.keys())
    service_weights = [SERVICES[s]["weight"] for s in service_names]

    while len(rows) < total:
        svc = random.choices(service_names, weights=service_weights, k=1)[0]
        cfg = SERVICES[svc]
        cause = random.choice(cfg["causes"])

        # Don't manufacture extra payments/connection_pool noise; the planted
        # cluster should be the whole of that pattern.
        if svc == "payments" and cause == "connection_pool":
            continue

        severity = weighted_choice(SEVERITY_WEIGHTS)
        low, high = DURATION_RANGES[severity]
        # Long tail: most resolve near the low end, some drag badly.
        duration = int(random.triangular(low, high, low + (high - low) * 0.25))

        title = random.choice(CAUSE_TITLES[cause]).format(svc=svc)

        rows.append({
            "service": svc,
            "severity": severity,
            "title": title,
            "opened_at": random_timestamp(),
            "duration_minutes": duration,
            "root_cause_category": cause,
            "owning_team": cfg["team"],
            "contact_name": cfg["contact"][0],
            "contact_phone": cfg["contact"][1],
        })

    rows.sort(key=lambda r: r["opened_at"])

    for r in rows:
        r["incident_id"] = f"INC-{counter:04d}"
        r["resolved_at"] = r["opened_at"] + timedelta(minutes=r["duration_minutes"])
        counter += 1

    return rows


def write_db(rows):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE incidents (
            incident_id          TEXT PRIMARY KEY,
            service              TEXT NOT NULL,
            severity             TEXT NOT NULL,
            title                TEXT NOT NULL,
            opened_at            TEXT NOT NULL,
            resolved_at          TEXT NOT NULL,
            duration_minutes     INTEGER NOT NULL,
            root_cause_category  TEXT NOT NULL,
            owning_team          TEXT NOT NULL,
            contact_name         TEXT NOT NULL,
            contact_phone        TEXT NOT NULL
        )
    """)
    conn.executemany("""
        INSERT INTO incidents VALUES
        (:incident_id, :service, :severity, :title, :opened_at, :resolved_at,
         :duration_minutes, :root_cause_category, :owning_team,
         :contact_name, :contact_phone)
    """, [
        {**r,
         "opened_at": r["opened_at"].isoformat(sep=" "),
         "resolved_at": r["resolved_at"].isoformat(sep=" ")}
        for r in rows
    ])
    conn.execute("CREATE INDEX idx_service ON incidents(service)")
    conn.execute("CREATE INDEX idx_severity ON incidents(severity)")
    conn.execute("CREATE INDEX idx_opened ON incidents(opened_at)")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    rows = build_incidents(200)
    write_db(rows)
    print(f"Wrote {len(rows)} incidents to {DB_PATH}")
    planted = [r["incident_id"] for r in rows
               if r["service"] == "payments"
               and r["root_cause_category"] == "connection_pool"]
    print(f"Planted payments cluster: {', '.join(planted)}")
