"""The full T1 submission field set (DOGFOOD T1): tagline, tech tags, an image
gallery of up to five, organizer-defined custom questions, and the gallery's
track and tech-tag filters."""
import csv
import io
from datetime import timedelta

from sqlmodel import select

from app.auth.models import Role, User
from app.auth.security import hash_password
from app.events.models import Event
from app.judging.models import JudgeAssignment, Rubric
from app.storage.service import LocalStorage, StorageError
from app.submissions.models import Submission, SubmissionStatus
from app.teams.models import Team, TeamMembership
from app.timeutil import utcnow

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844440000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000155e28f760000000049454e44ae426082"
)


def _user(session, email: str, role: Role = Role.participant) -> User:
    user = User(email=email, name=email.split("@")[0], role=role, password_hash=hash_password("supersecret1"))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login(client, email: str) -> None:
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    assert r.status_code == 200, r.text


def _event(session, slug: str, **fields) -> Event:
    owner = _user(session, f"{slug}-owner@example.com", Role.organizer)
    event = Event(
        slug=slug, name="Fields Event",
        start_at=utcnow() - timedelta(days=1), end_at=utcnow() + timedelta(days=1),
        created_by_id=owner.id, tracks=["Tools", "Apps"], **fields,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def _team(session, event: Event, email: str, name: str) -> Team:
    member = _user(session, email)
    team = Team(event_id=event.id, name=name)
    session.add(team)
    session.commit()
    session.refresh(team)
    session.add(TeamMembership(team_id=team.id, user_id=member.id))
    session.commit()
    return team


def _entry(session, event: Event, name: str, **fields) -> Submission:
    team = Team(event_id=event.id, name=name)
    session.add(team)
    session.commit()
    session.refresh(team)
    submission = Submission(
        team_id=team.id, event_id=event.id, title=name, description="d", status=SubmissionStatus.submitted, **fields
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)
    return submission


# ---------------------------------------------------------------------------
# Tagline and tech tags
# ---------------------------------------------------------------------------

def test_tagline_and_tech_tags_save_clean_and_validate(client, session):
    event = _event(session, "fields-tags")
    team = _team(session, event, "fields-tags@example.com", "Taggers")
    _login(client, "fields-tags@example.com")
    url = f"/api/teams/{team.id}/submission"

    r = client.patch(url, json={"tagline": "  One   line  ", "tech_tags": [" Python ", "python", "Post  gres", ""]})
    assert r.status_code == 200, r.text
    assert r.json()["tagline"] == "One line"
    assert r.json()["tech_tags"] == ["Python", "Post gres"], "trimmed, and deduplicated case-insensitively"

    assert client.patch(url, json={"tagline": "x" * 141}).status_code == 422
    assert client.patch(url, json={"tech_tags": [f"t{i}" for i in range(11)]}).status_code == 422
    assert client.patch(url, json={"tech_tags": ["y" * 31]}).status_code == 422
    # Both optional: a draft with neither still autosaves and submits.
    assert client.patch(url, json={"title": "T", "description": "D"}).status_code == 200
    assert client.post(f"{url}/submit").status_code == 200


def test_gallery_shows_tagline_and_tags_and_searches_them(client, session):
    event = _event(session, "fields-search")
    _entry(session, event, "Alpha", tagline="Finds flaky tests", tech_tags=["Rust"])
    _entry(session, event, "Beta", tagline="Plans meetings", tech_tags=["Python"])

    items = client.get(f"/api/gallery?event_id={event.id}").json()
    by_title = {i["title"]: i for i in items}
    assert by_title["Alpha"]["tagline"] == "Finds flaky tests" and by_title["Alpha"]["tech_tags"] == ["Rust"]

    assert [i["title"] for i in client.get(f"/api/gallery?event_id={event.id}&q=flaky").json()] == ["Alpha"]
    assert [i["title"] for i in client.get(f"/api/gallery?event_id={event.id}&q=python").json()] == ["Beta"]

    detail = client.get(f"/api/submissions/{by_title['Beta']['id']}").json()
    assert detail["tagline"] == "Plans meetings" and detail["tech_tags"] == ["Python"]


# ---------------------------------------------------------------------------
# Gallery filters
# ---------------------------------------------------------------------------

def test_gallery_filters_by_track_and_tag_on_the_server(client, session):
    event = _event(session, "fields-filter")
    _entry(session, event, "Tools Rust", track="Tools", tech_tags=["Rust", "CLI"])
    _entry(session, event, "Tools Py", track="Tools", tech_tags=["python"])
    _entry(session, event, "Apps Rust", track="Apps", tech_tags=["rust"])
    base = f"/api/gallery?event_id={event.id}"

    def titles(query: str) -> set[str]:
        return {i["title"] for i in client.get(base + query).json()}

    assert titles("&track=Tools") == {"Tools Rust", "Tools Py"}
    assert titles("&tag=RUST") == {"Tools Rust", "Apps Rust"}, "tags match lowercased"
    assert titles("&track=Tools&tag=rust") == {"Tools Rust"}
    assert titles("&track=Nope") == set()
    assert client.get(f"/api/gallery/tags?event_id={event.id}").json() == ["cli", "python", "rust"]


# ---------------------------------------------------------------------------
# Image gallery
# ---------------------------------------------------------------------------

def test_a_team_adds_up_to_five_images_and_the_first_is_the_thumbnail(client, session):
    event = _event(session, "fields-images")
    team = _team(session, event, "fields-images@example.com", "Pictures")
    _login(client, "fields-images@example.com")
    client.patch(f"/api/teams/{team.id}/submission", json={"title": "Pics"})
    url = f"/api/teams/{team.id}/submission/images"

    for i in range(5):
        r = client.post(url, files={"file": (f"{i}.png", PNG_1PX, "image/png")})
        assert r.status_code == 200, r.text
    images = r.json()
    assert len(images) == 5
    sixth = client.post(url, files={"file": ("6.png", PNG_1PX, "image/png")})
    assert sixth.status_code == 409

    sub = client.get(f"/api/teams/{team.id}/submission").json()
    assert [i["id"] for i in sub["images"]] == [i["id"] for i in images]
    assert sub["image_url"] == images[0]["url"], "the first image is the thumbnail"

    new_order = [images[3]["id"], images[0]["id"], images[1]["id"], images[2]["id"], images[4]["id"]]
    r = client.put(f"{url}/order", json={"image_ids": new_order})
    assert r.status_code == 200 and [i["id"] for i in r.json()] == new_order
    assert client.get(f"/api/teams/{team.id}/submission").json()["image_url"] == images[3]["url"]
    assert client.put(f"{url}/order", json={"image_ids": new_order[:4]}).status_code == 422

    r = client.delete(f"{url}/{images[3]['id']}")
    assert r.status_code == 200 and [i["id"] for i in r.json()] == new_order[1:]
    assert client.get(images[3]["url"]).status_code == 404, "a removed image stops being served"
    assert client.get(f"/api/teams/{team.id}/submission").json()["image_url"] == images[0]["url"]


def test_the_single_screenshot_endpoint_still_replaces_image_one(client, session):
    event = _event(session, "fields-legacy")
    team = _team(session, event, "fields-legacy@example.com", "Legacy")
    _login(client, "fields-legacy@example.com")
    client.patch(f"/api/teams/{team.id}/submission", json={"title": "Old client"})
    first = client.post(f"/api/teams/{team.id}/submission/images", files={"file": ("a.png", PNG_1PX, "image/png")})
    client.post(f"/api/teams/{team.id}/submission/images", files={"file": ("b.png", PNG_1PX, "image/png")})
    first_id = first.json()[0]["id"]

    r = client.post(f"/api/teams/{team.id}/submission/image", files={"file": ("c.png", PNG_1PX, "image/png")})
    assert r.status_code == 200
    sub = client.get(f"/api/teams/{team.id}/submission").json()
    assert len(sub["images"]) == 2
    assert sub["image_url"] == r.json()["image_url"] and sub["images"][0]["id"] == first_id, "replaced in place"


def test_gallery_uploads_keep_every_existing_check(client, session, tmp_path):
    event = _event(session, "fields-checks")
    team = _team(session, event, "fields-checks@example.com", "Checks")
    _team(session, event, "fields-outsider@example.com", "Outsiders")
    _login(client, "fields-checks@example.com")
    client.patch(f"/api/teams/{team.id}/submission", json={"title": "Checked"})
    url = f"/api/teams/{team.id}/submission/images"

    assert client.post(url, files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}).status_code == 422
    # Claims PNG, isn't one: the magic bytes give it away.
    fake = client.post(url, files={"file": ("x.png", b"GIF89a" + b"\x00" * 20, "image/png")})
    assert fake.status_code == 422 and "isn't a real image" in fake.json()["detail"]
    with_bad_bytes = LocalStorage(tmp_path)
    try:
        with_bad_bytes.save(b"\x00" * 10, "image/jpeg")
        raise AssertionError("a non-JPEG claiming to be one must be refused")
    except StorageError:
        pass

    _login(client, "fields-outsider@example.com")
    assert client.post(url, files={"file": ("x.png", PNG_1PX, "image/png")}).status_code == 403

    event.end_at = utcnow() - timedelta(minutes=1)
    session.add(event)
    session.commit()
    _login(client, "fields-checks@example.com")
    assert client.post(url, files={"file": ("x.png", PNG_1PX, "image/png")}).status_code == 400, "frozen after close"


def test_the_project_page_carries_the_whole_gallery(client, session):
    event = _event(session, "fields-detail")
    team = _team(session, event, "fields-detail@example.com", "Detail")
    _login(client, "fields-detail@example.com")
    client.patch(f"/api/teams/{team.id}/submission", json={"title": "Detail", "description": "D"})
    for name in ("a.png", "b.png"):
        client.post(f"/api/teams/{team.id}/submission/images", files={"file": (name, PNG_1PX, "image/png")})
    sub = client.post(f"/api/teams/{team.id}/submission/submit").json()
    detail = client.get(f"/api/submissions/{sub['id']}").json()
    assert len(detail["images"]) == 2 and detail["image_url"] == detail["images"][0]["url"]


# ---------------------------------------------------------------------------
# Custom questions
# ---------------------------------------------------------------------------

def _organizer_sets(client, session, event: Event, questions: list[dict]):
    email = f"{event.slug}-owner@example.com"
    _login(client, email)
    return client.put(f"/api/events/{event.id}/questions", json={"questions": questions})


def test_only_organizers_define_questions_and_at_most_ten(client, session):
    event = _event(session, "q-define")
    _team(session, event, "q-define@example.com", "Asked")
    _login(client, "q-define@example.com")
    assert client.put(f"/api/events/{event.id}/questions", json={"questions": []}).status_code == 403

    too_many = [{"prompt": f"Q{i}"} for i in range(11)]
    assert _organizer_sets(client, session, event, too_many).status_code == 422
    r = _organizer_sets(client, session, event, [{"prompt": "What did you build?", "required": True}])
    assert r.status_code == 200, r.text
    (question,) = r.json()
    assert question["id"] and question["required"] is True and question["public"] is False


def test_required_questions_block_submit_not_autosave(client, session):
    event = _event(session, "q-required")
    team = _team(session, event, "q-required@example.com", "Required")
    qs = _organizer_sets(client, session, event, [
        {"prompt": "Who is your target user?", "required": True},
        {"prompt": "Anything else?"},
    ]).json()
    required, optional = qs[0]["id"], qs[1]["id"]
    _login(client, "q-required@example.com")
    url = f"/api/teams/{team.id}/submission"

    assert client.patch(url, json={"title": "T", "description": "D"}).status_code == 200
    r = client.post(f"{url}/submit")
    assert r.status_code == 400 and "Who is your target user?" in r.json()["detail"]

    assert client.patch(url, json={"answers": {optional: "Nope"}}).status_code == 200
    r = client.patch(url, json={"answers": {required: "Busy on-call engineers"}})
    assert r.status_code == 200
    assert r.json()["answers"] == {optional: "Nope", required: "Busy on-call engineers"}, "answers merge"
    assert client.patch(url, json={"answers": {"q_nope": "x"}}).status_code == 422
    assert client.patch(url, json={"answers": {optional: "x" * 1001}}).status_code == 422
    assert client.post(f"{url}/submit").status_code == 200


def test_an_answered_question_cannot_be_deleted_only_hidden(client, session):
    event = _event(session, "q-hide")
    team = _team(session, event, "q-hide@example.com", "Hider")
    (q,) = _organizer_sets(client, session, event, [{"prompt": "Stack?", "required": True}]).json()
    _login(client, "q-hide@example.com")
    client.patch(f"/api/teams/{team.id}/submission", json={"title": "T", "description": "D", "answers": {q["id"]: "Go"}})

    r = _organizer_sets(client, session, event, [])
    assert r.status_code == 409 and "Hide it instead" in r.json()["detail"]
    r = _organizer_sets(client, session, event, [{**q, "hidden": True}])
    assert r.status_code == 200 and r.json()[0]["hidden"] is True
    # A hidden question stops being required, and an unanswered one can go.
    (extra,) = [x for x in _organizer_sets(client, session, event, [{**q, "hidden": True}, {"prompt": "New"}]).json()
                if x["prompt"] == "New"]
    assert _organizer_sets(client, session, event, [{**q, "hidden": True}]).status_code == 200
    assert extra["id"] != q["id"]


def test_judges_see_every_answer_and_the_public_only_ticked_ones(client, session):
    event = _event(session, "q-see")
    team = _team(session, event, "q-see@example.com", "Seen")
    qs = _organizer_sets(client, session, event, [
        {"prompt": "Public one", "public": True},
        {"prompt": "Judges only"},
        {"prompt": "Retired", "hidden": True, "public": True},
    ]).json()
    _login(client, "q-see@example.com")
    url = f"/api/teams/{team.id}/submission"
    client.patch(url, json={
        "title": "T", "description": "D",
        "answers": {qs[0]["id"]: "Everyone may read this", qs[1]["id"]: "Only judges read this"},
    })
    sub_id = client.post(f"{url}/submit").json()["id"]
    # The hidden question's answer, written directly, as if given before it was hidden.
    sub = session.get(Submission, sub_id)
    sub.answers = {**sub.answers, qs[2]["id"]: "Old answer"}
    session.add(sub)
    session.commit()

    detail = client.get(f"/api/submissions/{sub_id}").json()
    assert [a["answer"] for a in detail["answers"]] == ["Everyone may read this"]

    judge = _user(session, "q-see-judge@example.com", Role.judge)
    session.add(Rubric(event_id=event.id, name="R", criteria=[{"key": "k", "label": "K", "weight": 1, "max_score": 10}]))
    assignment = JudgeAssignment(event_id=event.id, submission_id=sub_id, judge_id=judge.id)
    session.add(assignment)
    session.commit()
    _login(client, "q-see-judge@example.com")
    sheet = client.get(f"/api/assignments/{assignment.id}/sheet").json()
    assert [(a["prompt"], a["answer"]) for a in sheet["answers"]] == [
        ("Public one", "Everyone may read this"),
        ("Judges only", "Only judges read this"),
    ]


def test_answers_are_in_the_csv_and_round_trip_through_json(client, session):
    event = _event(session, "q-export")
    team = _team(session, event, "q-export@example.com", "Exported")
    (q,) = _organizer_sets(client, session, event, [{"prompt": "Why now?", "required": True, "public": True}]).json()
    _login(client, "q-export@example.com")
    client.patch(f"/api/teams/{team.id}/submission", json={
        "title": "T", "description": "D", "tagline": "Tag line", "tech_tags": ["Go"], "answers": {q["id"]: "Because"},
    })

    _login(client, "q-export-owner@example.com")
    rows = list(csv.reader(io.StringIO(client.get(f"/api/events/{event.id}/export/submissions.csv").text)))
    header, row = rows[0], rows[1]
    assert "Q: Why now?" in header and row[header.index("Q: Why now?")] == "Because"
    assert row[header.index("tagline")] == "Tag line" and row[header.index("tech_tags")] == "Go"

    backup = client.get(f"/api/events/{event.id}/export.json").json()
    assert backup["event"]["questions"][0]["id"] == q["id"]
    assert backup["submissions"][0]["answers"] == {q["id"]: "Because"}
    r = client.post("/api/events/import", json={
        **backup["event"], "slug": "q-export-copy", "rubrics": backup["rubrics"],
        "teams": backup["teams"], "submissions": backup["submissions"],
    })
    assert r.status_code == 201, r.text
    copy = session.exec(select(Event).where(Event.slug == "q-export-copy")).one()
    assert copy.questions == backup["event"]["questions"]
    copied = session.exec(select(Submission).where(Submission.event_id == copy.id)).one()
    assert copied.answers == {q["id"]: "Because"}
    assert copied.tagline == "Tag line" and copied.tech_tags == ["Go"]
