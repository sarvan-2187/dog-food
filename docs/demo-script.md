# 5-minute demo script

The DOGFOOD brief asks for a 5-minute video walking one full event lifecycle:
create, submit, judge, publish. This is the shot list. Record against a fresh stack
(`docker compose down -v && docker compose up --build`) at `http://localhost:8000`.
Seeded accounts are in the README.

| Time | Who | Show | Say |
|---|---|---|---|
| 0:00–0:20 | Terminal | `docker compose up`, the boot log printing the checker headers, then `acceptance-report.txt` (7/7) | One command, seeded, works with the network off. The checker's receipt is committed. |
| 0:20–1:00 | Organizer `alice@` | **Events → New**: name, dates, tracks, prizes, team cap. **Rubric**: two rubrics, weights summing to 1.00. Publish. | Weighted, organizer-configured criteria: the thing the market leader can't do. |
| 1:00–1:50 | Participant `jordan@` | `dogfood-2026` → create a team, copy the invite link, submit: title, description, links, screenshot. Point at "Saving… / Saved" and the countdown. | Drafts autosave; the deadline is enforced by the server, not the page. |
| 1:50–2:10 | Terminal | `curl -X POST localhost:8000/api/teams/8/submission/submit -H "Cookie: session=demo-prt-2e88"` (a `sample-hack-2026` team) → refused | A closed event refuses writes over the API too. |
| 2:10–3:10 | Organizer → `judging-showcase-2026` | **Results**: run assignment (3 judges per project, conflicts skipped), judge progress. As judge `sam@`: the score form. | Deterministic assignment that knows about conflicts; a judge only ever sees their own ballots. |
| 3:10–3:30 | Terminal | judge B `curl`s judge A's scores → 403 | Role isolation lives in the backend. Hiding a button isn't isolation. |
| 3:30–4:10 | Organizer | **Results**: raw mean vs normalized rank, the CSV export. Open `JUDGING.md` briefly. | Per-judge z-scores: the judge who marks everything a 3 stops distorting the ranking. |
| 4:10–4:40 | Organizer, then a private window | **Community voting**: open voting, set **Who can vote** to *Anyone with the link*, hide counts until a time. In a private window vote with no account → counts hidden. | Access is set per event (open, email-confirmed or accounts), and hidden counts are withheld in the API response. |
| 4:40–5:00 | Organizer | Set the reveal time to now → public results, winners, a certificate PDF, the audit log. | Results published, every action audited, records signed and verifiable offline. |
