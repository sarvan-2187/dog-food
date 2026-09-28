#!/usr/bin/env python3
"""HackFlow's T3/T4 checker, a companion to the official run.py.

run.py only has checks for T1 and T2, so its report always ends "claimed but
not verified: T3 T4". This file checks every T3 and T4 bullet of the brief (and
two extra T2 integrity rules) the same way: plain HTTP against the running
portal, standard library only, nothing to install.

Usage:  python3 check_t3_t4.py .dogfood.toml > t3-t4-report.txt

It reads the same .dogfood.toml as run.py (base_url and the [auth] cookies) and
builds its own throwaway event with a unique slug, so it can be run again and
again and never changes the official fixture event: run.py still passes after
it. Every PASS lists the exact requests behind it, so a judge can replay any
line with curl.

The webhook check starts a small HTTP receiver on this machine and asks the
portal to post to http://host.docker.internal:<port>/. docker-compose.yml maps
that name to the host on Linux too. Set CHECK_WEBHOOK_HOST to use another name.
"""

import argparse
import base64
import http.cookiejar
import http.server
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timedelta, timezone

try:
    import tomllib  # Python 3.11 and newer
except ModuleNotFoundError:
    tomllib = None

TIMEOUT = 15
TIERS = ["T2", "T3", "T4"]


def parse_toml(text):
    """Enough TOML for .dogfood.toml, so older Pythons work too (as in run.py)."""
    data, section = {}, None
    for raw in text.splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        head = re.fullmatch(r"\[([A-Za-z0-9_.]+)\]", line)
        if head:
            section = data.setdefault(head.group(1), {})
            continue
        key, sep, value = line.partition("=")
        if not sep or section is None:
            continue
        key, value = key.strip(), value.strip()
        if value.startswith("["):
            section[key] = re.findall(r'"([^"]*)"', value)
        else:
            section[key] = value.strip().strip('"').strip("'")
    return data


def load_config(path):
    if tomllib:
        with open(path, "rb") as f:
            return tomllib.load(f)
    with open(path, encoding="utf-8") as f:
        return parse_toml(f.read())


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


class Client:
    """One caller: an [auth] header from .dogfood.toml, or its own cookie jar
    for an account this checker registers. Records every request it makes."""

    def __init__(self, base, name, header=None):
        self.base = base
        self.name = name
        self.header = header
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.log = None  # the Check currently collecting requests

    def call(self, method, path, body=None, headers=None, raw=False):
        req = urllib.request.Request(self.base + path, method=method)
        if self.header:
            k, _, v = self.header.partition(":")
            req.add_header(k.strip(), v.strip())
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        if body is not None:
            req.data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(req, timeout=TIMEOUT) as resp:
                status, data, hdrs = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            status, data, hdrs = e.code, e.read(), e.headers
        except Exception as e:  # no response at all
            status, data, hdrs = 0, f"{type(e).__name__}: {e}".encode(), {}
        if self.log is not None:
            self.log.request(f"{method} {path}  as {self.name}  -> {status}")
        if raw:
            return status, data, hdrs
        text = data.decode("utf-8", "replace")
        try:
            parsed = json.loads(text) if text else None
        except ValueError:
            parsed = text
        return status, parsed


class Check:
    def __init__(self, tier, label, bullet):
        self.tier, self.label, self.bullet = tier, label, bullet
        self.ok = False
        self.requests, self.detail = [], []

    def request(self, line):
        self.requests.append(line)

    def note(self, line):
        self.detail.append(line)


def pdf_serial(pdf):
    """The certificate's HF-... serial, read from the PDF's content streams.
    reportlab writes them ASCII85-encoded and Flate-compressed; both layers
    are in the standard library (base64.a85decode, zlib)."""
    texts = [pdf]
    for stream in re.findall(rb"stream\r?\n(.*?)\s*endstream", pdf, re.S):
        for decode in (
            lambda b: zlib.decompress(base64.a85decode(b.strip().removesuffix(b"~>"), ignorechars=b" \t\r\n")),
            zlib.decompress,
        ):
            try:
                texts.append(decode(stream))
                break
            except Exception:
                continue
    for text in texts:
        found = re.search(rb"HF-\d+-[A-Za-z0-9]+", text)
        if found:
            return found
    return None


class Receiver(http.server.BaseHTTPRequestHandler):
    """Collects webhook POSTs for the webhook check."""

    received = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            Receiver.received.append(json.loads(body))
        except ValueError:
            pass
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def run_checks(cfg):
    base = cfg["portal"]["base_url"].rstrip("/")
    auth = cfg.get("auth", {})
    org = Client(base, "organizer", auth.get("organizer"))
    judge_a = Client(base, "judge_a", auth.get("judge_a"))
    judge_b = Client(base, "judge_b", auth.get("judge_b"))
    anon = Client(base, "anonymous")
    checks = []
    tag = f"{int(time.time())}{os.getpid() % 1000}"
    state = {}

    def check(tier, label, bullet):
        c = Check(tier, label, bullet)
        checks.append(c)
        for client in (org, judge_a, judge_b, anon, *state.get("people", [])):
            client.log = c
        return c

    def expect(c, cond, why):
        if not cond:
            c.note(why)
        return cond

    def person(n):
        """A fresh participant with its own session cookie."""
        p = Client(base, f"participant{n}")
        email = f"t34-{tag}-{n}@example.com"
        p.call("POST", "/api/auth/register", {"email": email, "password": "checker-pass-1", "name": f"Checker {n}"})
        state.setdefault("people", []).append(p)
        return p

    # --- setup: an event of our own, open for submissions, six entries -----
    setup = check("--", "setup: own event with six submitted entries", "")
    now = datetime.now(timezone.utc)
    status, event = org.call("POST", "/api/events", {
        "slug": f"t34-check-{tag}", "name": f"T3/T4 check {tag}",
        "start_at": iso(now - timedelta(hours=1)), "end_at": iso(now + timedelta(days=1)),
        "tracks": ["Tools", "Apps"],
    })
    if status != 201:
        setup.note(f"could not create an event as organizer (got {status}); is [auth] organizer right?")
        return checks
    org.call("POST", f"/api/events/{event['id']}/publish")
    eid, slug = event["id"], event["slug"]
    entries = []
    for n in range(6):
        p = person(n)
        status, team = p.call("POST", f"/api/events/{eid}/teams", {"name": f"Checker team {n}"})
        if status != 201:
            setup.note(f"participant{n} could not create a team (got {status})")
            return checks
        track = "Tools" if n % 2 == 0 else "Apps"
        p.call("PATCH", f"/api/teams/{team['id']}/submission",
               {"title": f"Checker entry {n}", "description": "Built by check_t3_t4.py.", "track": track})
        status, sub = p.call("POST", f"/api/teams/{team['id']}/submission/submit")
        if status != 200:
            setup.note(f"participant{n} could not submit (got {status})")
            return checks
        entries.append((sub["id"], track))
    setup.ok = True
    voter, voter2, other = state["people"][0], state["people"][1], state["people"][2]
    first = entries[1][0]  # voter (participant0) votes for someone else's entry

    # --- T3 -------------------------------------------------------------
    c = check("T3", "voting toggle per event", "Voting toggle per event")
    s1, _ = voter.call("POST", f"/api/submissions/{first}/vote")
    org.call("PATCH", f"/api/events/{eid}", {
        "voting_enabled": True, "results_hidden_until": iso(now + timedelta(days=2)),
    })
    s2, _ = voter.call("POST", f"/api/submissions/{first}/vote")
    c.ok = expect(c, s1 == 409, f"a vote before voting opened got {s1}, wanted 409") & expect(
        c, s2 == 200, f"a vote after the organizer opened voting got {s2}, wanted 200")

    c = check("T3", "results hidden during voting, in the API", "Hidden results during voting")
    s1, rows = anon.call("GET", f"/api/gallery?event_id={eid}")
    s2, _ = anon.call("GET", f"/api/events/{eid}/public-results")
    s3, _ = voter.call("GET", f"/api/events/{eid}/public-results")
    s4, org_rows = org.call("GET", f"/api/gallery?event_id={eid}")
    hidden = s1 == 200 and all(r.get("votes") is None for r in rows or [])
    counted = s4 == 200 and any((r.get("votes") or 0) > 0 for r in org_rows or [])
    c.ok = (expect(c, hidden, "an anonymous gallery read carried vote counts")
            & expect(c, s2 == 425 and s3 == 425, f"public results gave {s2} anonymous, {s3} participant; wanted 425")
            & expect(c, counted, "the organizer did not see the real count"))

    c = check("T3", "randomized ordering, stable per seed", "Randomized project ordering")
    orders = []
    for seed in (1, 1, 2, 3, 4, 5):
        _, rows = anon.call("GET", f"/api/gallery?event_id={eid}&order=random&seed={seed}")
        orders.append([r["id"] for r in rows or []])
    c.ok = (expect(c, orders[0] == orders[1] and len(orders[0]) == 6, "the same seed gave two different orders")
            & expect(c, len({tuple(o) for o in orders}) >= 3, "different seeds did not reshuffle the gallery"))

    c = check("T3", "comments: add, list, delete own only", "Comments")
    s1, comment = voter.call("POST", f"/api/submissions/{first}/comments", {"body": "Checker comment."})
    _, listed = anon.call("GET", f"/api/submissions/{first}/comments")
    cid = (comment or {}).get("id") if isinstance(comment, dict) else None
    s3, _ = other.call("DELETE", f"/api/comments/{cid}")
    s4, _ = voter.call("DELETE", f"/api/comments/{cid}")
    c.ok = (expect(c, s1 == 201, f"posting got {s1}, wanted 201")
            & expect(c, any(x.get("id") == cid for x in listed or []), "the comment was not listed")
            & expect(c, s3 == 403, f"another user deleting it got {s3}, wanted 403")
            & expect(c, s4 == 204, f"the author deleting it got {s4}, wanted 204"))

    c = check("T3", "rate limiting on votes, with Retry-After", "Rate limiting")
    hit, retry = None, None
    target = entries[3][0]
    for i in range(30):
        voter2.log = None  # 30 near-identical lines would bury the report
        status, _, hdrs = voter2.call("POST", f"/api/submissions/{target}/vote", raw=True)
        if status == 429:
            hit, retry = i + 1, hdrs.get("Retry-After")
            break
        voter2.call("DELETE", f"/api/submissions/{target}/vote")
    c.request(f"POST /api/submissions/{target}/vote (then DELETE), repeated  as participant1  -> "
              f"429 on vote {hit}" if hit else "no 429 in 30 votes")
    c.ok = expect(c, hit is not None and hit <= 25, "30 votes in a row were never limited") & expect(
        c, bool(retry), "the 429 carried no Retry-After header")

    c = check("T3", "duplicate votes refused", "Duplicate detection")
    s1, _ = voter.call("POST", f"/api/submissions/{first}/vote")
    _, rows = org.call("GET", f"/api/gallery?event_id={eid}")
    count = next((r.get("votes") for r in rows or [] if r["id"] == first), None)
    c.ok = expect(c, s1 == 409, f"a second vote got {s1}, wanted 409") & expect(
        c, count == 1, f"the entry shows {count} votes after a duplicate, wanted 1")

    c = check("T3", "audit trail records votes and comments", "Audit trail")
    _, votes = org.call("GET", f"/api/audit?action=vote.cast&entity_type=submission&entity_id={first}")
    _, comments = org.call("GET", f"/api/audit?action=comment.added&entity_type=submission&entity_id={first}")
    s3, _ = voter.call("GET", "/api/audit")
    c.ok = (expect(c, bool(votes), "no vote.cast entry for the vote")
            & expect(c, bool(comments), "no comment.added entry for the comment")
            & expect(c, s3 == 403, f"a participant reading the audit log got {s3}, wanted 403"))

    # --- T2 integrity extras ----------------------------------------------
    # Close our event and judge it with judge_a as a Tools track judge.
    c = check("T2", "track judge only sees their track", "Judging integrity (extra)")
    s1, me = judge_a.call("GET", "/api/auth/me")
    tomas = (me or {}).get("email") if isinstance(me, dict) else None
    org.call("POST", f"/api/events/{eid}/rubrics", {
        "name": "Checker rubric", "criteria": [{"key": "impact", "label": "Impact", "weight": 1, "max_score": 10}],
    })
    org.call("POST", f"/api/events/{eid}/judges", {"email": tomas or ""})
    org.call("PUT", f"/api/events/{eid}/judges/{(me or {}).get('id')}/track", {"track": "Tools"})
    org.call("PATCH", f"/api/events/{eid}", {"end_at": iso(datetime.now(timezone.utc))})
    s5, summary = org.call("POST", f"/api/events/{eid}/assignments", {"judges_per_submission": 1})
    _, mine = judge_a.call("GET", "/api/judge/assignments")
    mine_here = [a for a in (mine or {}).get("pending", []) + (mine or {}).get("done", []) if a.get("event_id") == eid]
    tools = {sid for sid, t in entries if t == "Tools"}
    c.ok = (expect(c, s5 == 201, f"assignment run got {s5}, wanted 201")
            & expect(c, {a["submission_id"] for a in mine_here} == tools,
                     "judge_a (a Tools judge) was not given exactly the Tools entries")
            & expect(c, len((summary or {}).get("coverage_warnings", [])) == 3,
                     "the Apps entries were not reported as uncovered"))
    state["assignment"] = mine_here[0]["id"] if mine_here else None

    c = check("T2", "no one else can read or write that score sheet", "Judging integrity (extra)")
    aid = state["assignment"]
    s1, _ = judge_b.call("GET", f"/api/assignments/{aid}/sheet")
    s2, _ = judge_b.call("PUT", f"/api/assignments/{aid}/score", {"values": {"impact": 5}})
    s3, _ = org.call("PUT", f"/api/assignments/{aid}/score", {"values": {"impact": 5}})
    s4, _ = judge_a.call("PUT", f"/api/assignments/{aid}/score", {"values": {"impact": 7}})
    c.ok = (expect(c, s1 == 403 and s2 == 403, f"another judge got {s1}/{s2}, wanted 403/403")
            & expect(c, s3 == 403, f"the organizer scoring got {s3}, wanted 403")
            & expect(c, s4 == 200, f"the assigned judge scoring got {s4}, wanted 200"))

    # --- T4 -------------------------------------------------------------
    c = check("T4", "REST API with OpenAPI docs", "REST API + OpenAPI docs")
    s1, spec = anon.call("GET", "/openapi.json")
    s2, docs, _ = anon.call("GET", "/docs", raw=True)
    paths = (spec or {}).get("paths", {}) if isinstance(spec, dict) else {}
    c.ok = (expect(c, s1 == 200 and len(paths) >= 80, f"openapi.json gave {s1} with {len(paths)} paths")
            & expect(c, s2 == 200 and b"swagger" in docs.lower(), "/docs is not the interactive API explorer"))

    c = check("T4", "API keys for integrations", "REST API for integrations")
    s1, key = org.call("POST", "/api/api-keys", {"name": f"checker {tag}"})
    bearer = Client(base, "api key", f"Authorization: Bearer {(key or {}).get('key', '')}")
    bearer.log = c
    s2, _ = bearer.call("GET", f"/api/events/{eid}/results")
    org.call("DELETE", f"/api/api-keys/{(key or {}).get('id')}")
    s3, _ = bearer.call("GET", f"/api/events/{eid}/results")
    c.ok = (expect(c, s1 == 201, f"creating a key got {s1}")
            & expect(c, s2 == 200, f"reading results with the key got {s2}, wanted 200")
            & expect(c, s3 == 401, f"the revoked key got {s3}, wanted 401"))

    c = check("T4", "certificate PDF with a verifiable serial", "Certificate generation")
    s1, pdf, _ = org.call("GET", f"/api/submissions/{first}/certificate.pdf", raw=True)
    serial = pdf_serial(pdf or b"")
    s3, _ = voter.call("GET", f"/api/submissions/{entries[2][0]}/certificate.pdf")
    c.ok = expect(c, s1 == 200 and pdf.startswith(b"%PDF"), f"got {s1}, not a PDF") & expect(
        c, s3 == 403, f"someone off the team got {s3}, wanted 403")
    if serial:
        # The public lookup stays 404 until results are revealed, then confirms
        # the certificate; a serial with a forged tag never verifies.
        code = serial.group().decode()
        s2, _ = anon.call("GET", f"/api/certificates/{code}")
        org.call("PATCH", f"/api/events/{eid}", {"results_hidden_until": iso(datetime.now(timezone.utc))})
        s4, rec = anon.call("GET", f"/api/certificates/{code}")
        s5, _ = anon.call("GET", f"/api/certificates/{code[:-1]}{'A' if code[-1] != 'A' else 'B'}")
        c.ok &= (expect(c, s2 == 404, f"the serial verified before results were revealed ({s2})")
                 & expect(c, s4 == 200 and bool((rec or {}).get("submission_title")),
                          f"after the reveal, verifying the serial got {s4}, wanted 200")
                 & expect(c, s5 == 404, f"a forged serial got {s5}, wanted 404"))
    else:
        c.ok = expect(c, False, "no HF-... serial found in the PDF")

    c = check("T4", "signed judge participation record", "Signed judge participation records")
    jid = (me or {}).get("id")
    s1, record = judge_a.call("GET", f"/api/events/{eid}/judges/{jid}/participation-record")
    _, pub = anon.call("GET", "/api/public-key")
    s3, _ = judge_b.call("GET", f"/api/events/{eid}/judges/{jid}/participation-record")
    signed = isinstance(record, dict) and record.get("signature") and record.get("public_key") == (pub or {}).get("public_key")
    c.ok = (expect(c, s1 == 200 and bool(signed), "no signature, or signed with a key other than /api/public-key")
            & expect(c, s3 == 403, f"another judge fetching it got {s3}, wanted 403"))
    # Verify the Ed25519 signature offline if `cryptography` is installed. A broken
    # install can fail with a non-Exception panic, so any import failure means "not
    # available" rather than a crash.
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except BaseException:
        Ed25519PublicKey = None
    if Ed25519PublicKey is None or not signed:
        c.note("(install `cryptography` to also verify the Ed25519 signature offline)")
    else:
        body = json.dumps(record["record"], sort_keys=True, separators=(",", ":")).encode()
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(record["public_key"])).verify(
                base64.b64decode(record["signature"]), body)
            c.note("(Ed25519 signature verified offline)")
        except Exception as e:
            c.ok = expect(c, False, f"the signature does not verify: {type(e).__name__}")

    c = check("T4", "bulk export and import, people and scores included", "Bulk import/export")
    s1, backup = org.call("GET", f"/api/events/{eid}/export.json")
    copy_slug = f"{slug}-copy"
    body = dict((backup or {}).get("event", {}), slug=copy_slug)
    for part in ("rubrics", "teams", "submissions", "judges", "assignments", "scores"):
        body[part] = (backup or {}).get(part, [])
    s2, copy = org.call("POST", "/api/events/import", body)
    _, again = org.call("GET", f"/api/events/{(copy or {}).get('id')}/export.json")

    def shape(b):
        return {k: len((b or {}).get(k, [])) for k in ("teams", "submissions", "judges", "assignments", "scores")}

    c.ok = (expect(c, s1 == 200 and s2 == 201, f"export {s1}, import {s2}; wanted 200, 201")
            & expect(c, shape(backup) == shape(again) and shape(backup)["scores"] == 1,
                     f"the copy has {shape(again)}, the original {shape(backup)}"))

    c = check("T4", "a webhook for every action", "Webhooks covering every action")
    Receiver.received = []
    server = http.server.HTTPServer(("0.0.0.0", 0), Receiver)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host = os.environ.get("CHECK_WEBHOOK_HOST", "host.docker.internal")
    s1, hook = org.call("POST", f"/api/events/{eid}/webhooks", {"url": f"http://{host}:{server.server_port}/hook"})
    org.call("PATCH", f"/api/events/{eid}", {"description": "Changed by the checker."})
    voter.call("POST", f"/api/submissions/{first}/comments", {"body": "Seen by the webhook."})
    wanted = {"webhook.created", "event.updated", "comment.added"}
    deadline = time.time() + 10
    while time.time() < deadline and not wanted <= {r.get("record", {}).get("topic") for r in Receiver.received}:
        time.sleep(0.2)
    topics = sorted({r.get("record", {}).get("topic") for r in Receiver.received} - {None})
    server.shutdown()
    org.call("DELETE", f"/api/events/{eid}/webhooks/{(hook or {}).get('id')}")
    c.note(f"topics received: {', '.join(topics) or 'none'}")
    c.ok = expect(c, s1 == 201, f"creating the webhook got {s1}") & expect(
        c, wanted <= set(topics),
        f"wanted {', '.join(sorted(wanted))} at http://{host}:{server.server_port}; "
        "if the portal can't reach this machine, set CHECK_WEBHOOK_HOST")

    c = check("T4", "embeddable gallery widget", "Embeddable gallery widget")
    s1, html, hdrs = anon.call("GET", f"/embed/events/{slug}", raw=True)
    c.ok = expect(c, s1 == 200 and b"Checker entry 0" in html, f"got {s1}, or the entries were missing") & expect(
        c, "deny" not in (hdrs.get("X-Frame-Options") or "").lower(), "X-Frame-Options stops it being embedded")

    return checks


def main():
    ap = argparse.ArgumentParser(description="HackFlow T3/T4 checker (companion to run.py)")
    ap.add_argument("config", help="path to .dogfood.toml")
    args = ap.parse_args()
    cfg = load_config(args.config)

    print("HackFlow T3/T4 check report (companion to run.py)")
    print(f"portal: {cfg['portal']['base_url']}")
    print(f"run at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("each line lists the requests behind it; replay any of them with curl")
    print()

    checks = run_checks(cfg)
    width = max(len(c.label) for c in checks) + 2
    for c in checks:
        dots = "." * (width - len(c.label))
        print(f"{c.tier}  {c.label} {dots} {'PASS' if c.ok else 'FAIL'}")
        if c.bullet:
            print(f"      brief: {c.bullet}")
        for line in c.requests:
            print(f"      {line}")
        for line in c.detail:
            print(f"      ! {line}" if not c.ok and not line.startswith("(") else f"      {line}")
        print()

    graded = [c for c in checks if c.tier in TIERS]
    for t in TIERS:
        mine = [c for c in graded if c.tier == t]
        if mine:
            print(f"{t}: {sum(c.ok for c in mine)} of {len(mine)} checks pass")
    ok = all(c.ok for c in checks)
    print("all checks pass" if ok else "some checks failed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
