# HackFlow — User Manual (v1)

This manual walks through HackFlow one screen at a time, in the order you will actually
meet them. Every screenshot in it was taken from a real running copy of the software on
its built-in sample data — nothing here is a mock-up or a drawing.

You do not need to be technical to use this manual. If you can use a website, you can use
HackFlow.

**Contents**

1. [What HackFlow is](#1-what-hackflow-is)
2. [Getting in](#2-getting-in)
3. [The four kinds of account](#3-the-four-kinds-of-account)
4. [The guided tour](#4-the-guided-tour)
5. [For participants — entering a hackathon](#5-for-participants--entering-a-hackathon)
6. [For judges — scoring projects](#6-for-judges--scoring-projects)
7. [For organizers — running the event](#7-for-organizers--running-the-event)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. What HackFlow is

HackFlow runs a hackathon from beginning to end: people sign up, form teams, write up their
projects, judges score them fairly, and results are published at a time the organizer
chooses.

It is one self-contained website. There is no separate app to install, no third-party
service to sign up for, and it keeps working with the internet disconnected.

---

## 2. Getting in

If someone has already set HackFlow up for you, they will have given you a web address —
open it and skip to the login screen below.

If you are setting it up yourself, you need [Docker](https://www.docker.com/) installed.
Open a terminal in the project folder and run one command:

```bash
docker compose up
```

Wait until it stops printing new lines, then open **http://localhost:8000** in your browser.
The site sets itself up and fills itself with sample data on first start — there is nothing
else to configure.

### Logging in

![The login screen](docs/screenshots/manual/01-login.png)

Enter your email and password and choose **Log in**.

The sample data comes with accounts you can use to look around. Each row is a different
kind of account, so you can see how the site changes depending on who you are:

| Kind of account | Email | Password |
|---|---|---|
| Organizer | `alice@example.com` | `organizer-pass1` |
| Admin | `priya@example.com` | `admin-pass123` |
| Judge | `sam@example.com` | `judge-pass123` |
| Participant | `jordan@example.com` | `participant-pass1` |

### Creating your own account

![The sign-up screen](docs/screenshots/manual/02-register.png)

Choose **Sign up** if you do not have an account. You need a name, an email address, and a
password of at least eight characters.

Anyone who signs up publicly becomes a **participant** — somebody who enters projects.
Judge, organizer, and admin accounts cannot be self-created, on purpose: those roles can see
scores, so somebody already trusted has to grant them. (A judge is brought in by invitation
link; see section 7.)

---

## 3. The four kinds of account

What you see across the top of the site changes depending on which kind of account you have.
You are never shown a button that would refuse you.

| Account | What it is for | What it can do |
|---|---|---|
| **Participant** | Entering the hackathon | Join or create a team, write and submit a project, browse and vote in the gallery |
| **Judge** | Scoring entries | See only the projects assigned to them, and score those |
| **Organizer** | Running an event | Create and configure events, write scorecards, invite judges, assign judging, publish results, export data |
| **Admin** | Running the whole site | Everything an organizer can do, across all events |

---

## 4. The guided tour

The first time you log in, HackFlow offers a short tour of the screens you will use. It is
tailored to your kind of account — a judge and an organizer are shown different things.

![The guided tour welcoming a new participant](docs/screenshots/manual/03-tour-participant-welcome.png)

- **Next** and **Back** move through it.
- **Escape**, or the **×**, leaves at any point.
- It highlights the real thing it is describing, like the **My teams** tab here:

![The tour highlighting the My teams tab](docs/screenshots/manual/04-tour-participant-teams.png)

You only get it automatically once. To see it again at any time, open **Profile** and choose
**Replay the guided tour**.

---

## 5. For participants — entering a hackathon

### Step 1 — Open the hackathon

Choose **Events** in the menu, then click the hackathon you are entering.

![An event page showing dates, themes and prizes](docs/screenshots/manual/05-event-detail.png)

This page is the hackathon's front page. It shows:

- **The countdown** — how long you have left. This is the real deadline, not a suggestion:
  when it runs out the site stops accepting changes to your project.
- **Tracks** — the themes you can enter under, if the organizer set any up.
- **Prizes** — what is on offer.
- **Your team**, once you have one, with the invite link to share.

### Step 2 — Get on a team

You enter as a team, even if you are alone in it. There are two ways onto one.

**If you are starting the team:** choose **Create a team** on the event page, give it a name,
and you will be shown an **invite link**. Send that link to the people joining you.

**If somebody invited you:** open the link they sent. You will be added and shown a
confirmation. Opening the same link again is harmless — it just tells you that you are
already on the team.

**Teams have a size limit** — usually four people, set by the organizer. Once a team is full,
its invite link stops working and the page says so plainly, rather than failing silently.

You can see your teams at any time under **My teams**:

![The My teams screen](docs/screenshots/manual/06-my-teams.png)

The `2 / 4 members` on each card is the team's current size against the limit.

### Step 3 — Write up your project

From your team, choose **Go to your submission**. Each team gets exactly one project page.

![The project submission screen](docs/screenshots/manual/07-submission.png)

Important things about this screen:

- **It saves by itself.** There is no Save button to forget. A small marker near each field
  tells you whether your work is *Saving…*, *Saved*, or has *Unsaved changes*.
- **The deadline is always on screen**, at the top, so it can never take you by surprise.
- **Track** is a drop-down when the organizer has set up themes, so you cannot mistype it.
- You can keep editing right up to the deadline, even after you have submitted.

When you are ready, choose **Submit for judging**. Your project then appears in the public
gallery. You can still edit it until the deadline passes.

### Step 4 — Browse and vote

**Gallery** shows everything that has been submitted. Pick the hackathon, then browse.

![The public gallery](docs/screenshots/manual/08-gallery.png)

Click any project to read it in full, and — if the organizer has turned voting on — to vote
for it and leave a comment:

![A project page with voting and comments](docs/screenshots/manual/18-submission-detail-voting.png)

A few things are deliberately true here:

- **One vote per person per project**, and you can take your vote back.
- **Vote counts stay hidden** until the organizer's chosen reveal time, so an early lead
  cannot snowball. They are genuinely hidden, not just left off the screen.
- **The order is shuffled** so the projects at the top do not get an unfair advantage.

### Your account

**Profile** holds your name, email, photo, the log-out button, and the tour replay button.

![The profile screen](docs/screenshots/manual/09-profile.png)

---

## 6. For judges — scoring projects

### Step 1 — Accept your invitation

Judges join by invitation only. Your organizer will send you a link; open it while logged in
and accept. Your account becomes a judge account, and a **Judging** tab appears in the menu.

### Step 2 — Your list

**Judging** is your home base.

![The judge dashboard](docs/screenshots/manual/14-judge-dashboard.png)

It shows how many of your assigned projects you have finished, and lists what is left. You
are shown **only** the projects assigned to you.

Choose **Score now** on any of them.

### Step 3 — Score a project

![The scoring form](docs/screenshots/manual/16-score-form.png)

The form is built from the scorecard the organizer wrote. Each item shows:

- **its weight** — how much it counts toward the total, and
- **what it is out of** — usually 10.

An event can use more than one scorecard (here, a *Technical Rubric* and a *Presentation
Rubric*), and they are combined into this single form. You do not need to do any arithmetic;
the site handles the weighting.

You can leave a comment with your score, and you can come back and change a score you have
already given.

### Three things worth knowing

**You are scoring alone, on purpose.** You cannot see any other judge's scores or comments,
and they cannot see yours. This is enforced by the server, not merely hidden on screen.

**You are never given a project from your own team.** The assignment step checks this
automatically.

**Being a tough marker will not hurt anyone.** After scoring finishes, HackFlow compares each
judge against their own average and adjusts for it. A consistently strict judge does not drag
their projects down the rankings, and a generous one does not lift theirs up. So score the
way that feels honest to you — you do not need to guess what the other judges are doing.

*(If you want the mathematics behind that, it is written up in `JUDGING.md`.)*

---

## 7. For organizers — running the event

### Step 1 — Create the event

Choose **Create event**.

![The create-event form](docs/screenshots/manual/17-create-event.png)

You give it a name, a web address slug, a description, start and end dates, the themes teams
may enter under, the prizes, and the largest team you will allow. Only the name, slug, and
dates are required — everything else can be added later.

### Step 2 — Adjust settings at any time

From the event page, choose **Event settings**.

![The event settings screen](docs/screenshots/manual/11-event-settings.png)

Here you can change the maximum team size, add or remove tracks, and edit the prize list.

Raising or lowering the team-size limit only affects **new** joins — a team that is already
larger than a reduced limit is left alone rather than having someone thrown out.

### Step 3 — Write the scorecard

From the event page, choose **Judging rubric**.

![The rubric builder](docs/screenshots/manual/12-rubric-builder.png)

A scorecard is a list of things judges mark on, each with a weight and a maximum. The
weights must add up to 100%, and the page tells you live whether they do, so you cannot save
something that does not add up.

You can create more than one scorecard for an event — for example *Technical* and
*Presentation* — and judges get them combined into one form.

**Scorecards lock once scoring starts.** As soon as the first judge submits a score, the
scorecard can no longer be edited. This is deliberate: it guarantees every project in the
event was measured against the same thing.

### Step 4 — Invite judges and hand out the work

From the event page, choose **Assignments & results**.

![The assignments and results screen](docs/screenshots/manual/13-assignments-results.png)

**To invite a judge**, fill in the small form in the *Judges* section and choose **Create
invitation**. You get a link to send them. You can set how long the link stays valid, and
optionally note who it was for.

**To hand out the judging**, choose **Assign judges**. HackFlow gives each submitted project
three judges, spreads the work evenly, and never gives anyone a project from their own team.
Running it a second time only fills gaps — it will not duplicate work anyone already has.

### Step 5 — Voting and results

The same screen controls the public side:

- **Community voting** can be opened or closed whenever you like.
- **Hide vote counts until** sets the moment results become public. Until then, nobody
  outside the organizing team can see counts or standings.
- **Exports** gives you a spreadsheet of participants, projects, assignments, raw scores, or
  final normalized standings, at any point during the event.

### Optional — notifications to other systems

Further down the **Event settings** screen you can give HackFlow a web address to notify when
something happens: a project is submitted, judging is assigned, a score arrives, or results
go live. It is useful for feeding a Discord or Slack channel.

Each notification is cryptographically signed, so the system receiving it can confirm it
genuinely came from your HackFlow and was not altered on the way. This is entirely optional —
leave it empty and HackFlow never contacts anything outside itself.

---

## 8. Troubleshooting

**The page says my deadline has passed but I am not finished.**
Deadlines are enforced by the server and cannot be worked around from the browser. Ask your
organizer — they can move the event's end date from **Event settings**.

**My invite link does not work.**
Three possible reasons, and the page will tell you which: the team is already full, the link
has expired (organizers choose how long they last), or you are already on that team.

**I cannot see vote counts or rankings.**
That is intended until the organizer's reveal time. The numbers are genuinely withheld, not
just hidden from view, so refreshing or trying another browser will not reveal them early.

**I am a judge but I cannot see a project I want to score.**
You can only score what you were assigned. If you believe something is missing, ask the
organizer to re-run assignment.

**The scorecard will not save.**
The weights must total exactly 100%. The page shows the running total as you type. If it is
locked instead, scoring has already begun and it can no longer be changed.

**I want the tour again.**
**Profile** → **Replay the guided tour**.

**I want to start over with clean sample data.**
Stop the site and run:

```bash
docker compose down -v
docker compose up
```

This erases everything and re-creates the original sample data. Do not run it on a real
event — it deletes real entries too.

---

## Where to go next

This manual covers using HackFlow. If you want to understand or modify how it works:

- **`README.md`** — what it is and how to run it
- **`ARCHITECTURE.md`** — how the system is put together
- **`DATA-MODEL.md`** — what is stored, and how to get data in and out
- **`JUDGING.md`** — the assignment algorithm and the normalization mathematics
- **`THREAT-MODEL.md`** — the abuse scenarios it defends against, and how
