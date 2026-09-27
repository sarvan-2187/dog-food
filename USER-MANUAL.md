# HackFlow User Manual (v2)

This manual walks through HackFlow one screen at a time, in the order you will actually
meet them. Every screenshot in it was taken from a real running copy of the software on
its built-in sample data. Nothing here is a mock-up or a drawing. (They are regenerated
with `cd web && node scripts/manual-screenshots.mjs` against a running `docker compose up`.)

You do not need to be technical to use this manual. If you can use a website, you can use
HackFlow.

**Contents**

1. [What HackFlow is](#1-what-hackflow-is)
2. [Getting in](#2-getting-in)
3. [The four kinds of account](#3-the-four-kinds-of-account)
4. [The guided tour](#4-the-guided-tour)
5. [For participants: entering a hackathon](#5-for-participants-entering-a-hackathon)
6. [For judges: scoring projects](#6-for-judges-scoring-projects)
7. [For organizers: running the event](#7-for-organizers-running-the-event)
8. [For admins: running the site](#8-for-admins-running-the-site)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. What HackFlow is

HackFlow runs a hackathon from beginning to end: people sign up, form teams, write up their
projects, judges score them fairly, and results are published at a time the organizer
chooses.

It is one self-contained website. There is no separate app to install, no third-party
service to sign up for, and it keeps working with the internet disconnected.

---

## 2. Getting in

If someone has already set HackFlow up for you, they will have given you a web address.
Open it and skip to the login screen below.

If you are setting it up yourself, you need [Docker](https://www.docker.com/) installed.
Open a terminal in the project folder and run one command:

```bash
docker compose up
```

Wait until it stops printing new lines, then open **http://localhost:8000** in your browser.
The site sets itself up and fills itself with sample data on first start, and there is nothing
else to configure.

### Putting it online (optional)

To give people a web address instead of `localhost`, the project includes a ready-made setup
for [Render](https://render.com), which has a free plan and needs no credit card.

1. Put the project in your own GitHub repository.
2. On Render, sign in with GitHub, choose **New → Blueprint**, pick the repository, and
   choose **Apply**. Render reads `render.yaml` and creates the site and its database. The
   first build takes 5–10 minutes.
3. When it is live, open the site's **Environment** tab and set `APP_BASE_URL` to its
   address (for example `https://hackflow-xxxx.onrender.com`).
4. Optional: the free plan puts the site to sleep after 15 minutes without visitors, and
   the next visit waits about a minute. A free monitor such as
   [UptimeRobot](https://uptimerobot.com) that opens `/healthz` every 5 minutes keeps it
   awake.

Know the free plan's limits before relying on it:

- **Uploaded images and the signing key are erased whenever the site restarts.**
  Certificates and judge records signed before a restart will stop verifying.
- **The free database expires after about 30 days.**
- **The sample accounts below work on the public site**, so anyone can sign in as the
  sample organizer. Fine for a demo; change those passwords before a real event.

For a real event, run `docker compose up` on a server of your own instead, where nothing is
erased.

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

Anyone who signs up publicly becomes a **participant**, somebody who enters projects.
Judge, organizer, and admin accounts cannot be self-created, on purpose: those roles can see
scores, so somebody already trusted has to grant them. (Judges and organizers are brought in
by invitation link; see sections 7 and 8.)

### Forgot your password?

![The forgot-password screen](docs/screenshots/manual/19-forgot-password.png)

Choose **Forgot password?** under the password box on the login page.

- **If your event has email set up**, enter your address and you will get a link. It works
  once and expires after 30 minutes. Nothing arriving? Check spam, then ask again.
- **If it does not**, the page tells you so. Ask an organizer at the help desk or in your
  event's channel for a reset link (section 7, *Helping someone sign in*). It works once and
  expires after an hour.

Either way, choosing the new password signs you straight in and signs you out everywhere
else.

---

## 3. The four kinds of account

What you see across the top of the site changes depending on which kind of account you have.
You are never shown a button that would refuse you.

| Account | What it is for | What it can do |
|---|---|---|
| **Participant** | Entering the hackathon | Join or create a team, write and submit a project, browse, vote and comment in the gallery |
| **Judge** | Scoring entries | See only the projects assigned to them, score those, and step back from a project they have a conflict with |
| **Organizer** | Running an event | Create and publish events, write scorecards, invite judges, assign judging, post announcements, pick winners, publish results, export data, help people sign in |
| **Admin** | Running the whole site | Everything an organizer can do, plus managing accounts and inviting organizers |

---

## 4. The guided tour

The first time you log in, HackFlow offers a short tour of the screens you will use. It is
tailored to your kind of account: a participant, a judge and an organizer are each shown
different things.

![The guided tour welcoming a new participant](docs/screenshots/manual/03-tour-participant-welcome.png)

- **Next** and **Back** move through it.
- **Escape**, or the **×**, leaves at any point.
- It highlights the real thing it is describing, like the **My teams** tab here:

![The tour highlighting the My teams tab](docs/screenshots/manual/04-tour-participant-teams.png)

Organizers get a longer tour (ten steps, covering judging progress, winners and
announcements), and judges get one about scoring alone and fairly:

| Organizer tour | Judge tour |
|---|---|
| ![The organizer tour](docs/screenshots/manual/10-tour-organizer.png) | ![The judge tour](docs/screenshots/manual/15-tour-judge.png) |

You only get it automatically once. To see it again at any time, open **Profile** and choose
**Replay the guided tour**.

---

## 5. For participants: entering a hackathon

### Step 1: Open the hackathon

Choose **Events** in the menu, then click the hackathon you are entering.

![An event page showing dates, tracks, prizes and announcements](docs/screenshots/manual/05-event-detail.png)

This page is the hackathon's front page. It shows:

- **The countdown**: how long you have left. This is the real deadline, not a suggestion:
  when it runs out the site stops accepting changes to your project.
- **Tracks**: the themes you can enter under, if the organizer set any up.
- **Prizes**: what is on offer.
- **Announcements**: messages from the organizers ("demos start at 5"). The newest ones
  also appear on your **Dashboard**, so you do not have to keep checking.
- **Rules** and **How projects are judged**: the scorecard judges will use, so you know
  what counts before you start.
- **Your team**, once you have one.

### Step 2: Get on a team

You enter as a team, even if you are alone in it. There are two ways onto one.

**If you are starting the team:** choose **Create a team** on the event page and give it a
name. You become its **captain** and get an **invite link** to send to the people joining
you.

**If somebody invited you:** open the link they sent. You will be added and shown a
confirmation. Opening the same link again is harmless. It just tells you that you are
already on the team.

You can be on **one team per hackathon**, and **teams have a size limit**, usually four
people, set by the organizer. Once a team is full, its invite link stops working and the page
says so plainly, rather than failing silently.

The **Your team** card on the event page is where the team is managed:

![The Your team card with captain controls](docs/screenshots/manual/20-your-team.png)

- **Copy** the invite link to share it. **New link** replaces it, so the old one stops
  working immediately. Useful if it was posted somewhere public.
- The **captain** can **Rename** the team, **Remove** someone, or **Make captain** to hand
  the role on.
- **Leave team** takes you off it (to join a different one, for example). If you were the
  captain, the longest-standing member takes over. The last member of a team cannot leave
  once it has submitted.

You can see all your teams at any time under **My teams**:

![The My teams screen](docs/screenshots/manual/06-my-teams.png)

The `2 / 4 members` on each card is the team's current size against the limit.

### Step 3: Write up your project

From your team, choose **Go to your submission**. Each team gets exactly one project page.

![The project submission screen](docs/screenshots/manual/07-submission.png)

Important things about this screen:

- **It saves by itself.** There is no Save button to forget. A small marker near each field
  tells you whether your work is *Saving…*, *Saved*, or has *Unsaved changes*.
- **The deadline is always on screen**, at the top, so it can never take you by surprise.
- **Track** is a drop-down when the organizer has set up themes, so you cannot mistype it.
- **Links for the judges**: fill in **Code repository**, **Live demo** and **Demo video**.
  Judges see them on their scoring screen.
- **A screenshot** of your project can be uploaded; it becomes the picture in the gallery.
- You can keep editing right up to the deadline, even after you have submitted.

When you are ready, choose **Submit for judging**. Your project then appears in the public
gallery. You can still edit it until the deadline passes.

If the organizers rule your entry ineligible, a red box at the top of this page says so
and gives their reason. The project leaves the gallery, voting and judging. Contact the
organizers if you think it's a mistake; they can reinstate it with one click, and nothing
you or the judges did is lost.

### Step 4: Browse and vote

**Gallery** shows everything that has been submitted. Pick the hackathon, then browse,
search, or change the order.

![The public gallery](docs/screenshots/manual/08-gallery.png)

Click any project to read it in full and, if the organizer has turned voting on, to vote
for it and leave a comment:

![A project page with voting and comments](docs/screenshots/manual/18-submission-detail-voting.png)

A few things are deliberately true here:

- **One vote per person per project**, and you can take your vote back.
- **Who can vote is the organizer's choice.** Usually you need to be logged in. Some events
  let anyone with the link vote, and some ask guests for an email address first. You will
  see a **Vote without an account** box, and the link emailed to you lets you vote from that
  browser.
- **Some events ask more of voters**, to stop one person voting from several accounts. You
  may need a verified email (see *Your account* below), or an account made before a date
  the organizer chose. If you can't vote, the message says which.
- **Vote counts stay hidden** until the organizer's chosen reveal time, so an early lead
  cannot snowball. They are genuinely hidden, not just left off the screen.
- **The order can be shuffled** so the projects at the top do not get an unfair advantage.

Once results are revealed, your team can download a **participation certificate** from your
project page.

### Your account

**Profile** holds your name, email, photo, password change, the log-out button, and the tour
replay button.

![The profile screen](docs/screenshots/manual/09-profile.png)

- **Name → Edit** changes how you appear.
- **Change password** signs you out on every other device.
- **Send verification link**, under your email, emails you a link that proves the address
  is yours. It works for 24 hours. Once you follow it, your profile shows **Verified**.
  Some events only count votes from verified accounts.

---

## 6. For judges: scoring projects

### Step 1: Accept your invitation

Judges join by invitation only. Your organizer will send you a link; open it while logged in
and accept. Your account becomes a judge account, you join that event's judging panel, and a
**Judging** tab appears in the menu.

### Step 2: Your list

**Judging** is your home base.

![The judge dashboard](docs/screenshots/manual/14-judge-dashboard.png)

- **Coming up** lists events you judge whose submissions have not closed yet, and when
  judging opens for each. Judging never starts while teams can still edit, so you always
  score the version that was actually submitted.
- The big number is how many of your assigned projects you have finished.
- **Still to score** lists what is left. You are shown **only** the projects assigned to you.
- If the organizer set a judging deadline, each project shows **Due** with the days left,
  and **Overdue** once it has passed. You can still score after it; the organizer just
  sees that it came in late.

Choose **Score now** on any of them.

### Step 3: Score a project

![The scoring form](docs/screenshots/manual/16-score-form.png)

The top of the form shows the project and the team's links (code, demo, video). Below it,
the form is built from the scorecard the organizer wrote. Each item shows:

- **its weight**: how much it counts toward the total, and
- **what it is out of**: usually 10.

An event can use more than one scorecard (here, a *Technical Rubric* and a *Presentation
Rubric*), and they are combined into this single form. The **Weighted total** updates as you
type, so you do not need to do any arithmetic.

You can leave a comment with your score, and you can come back and change a score you have
already given.

**If you know the team**, choose **I have a conflict of interest with this project** at the
bottom. The project goes to another judge, will not be assigned to you again, and the
organizer sees your note.

### Three things worth knowing

**You are scoring alone, on purpose.** You cannot see any other judge's scores or comments,
and they cannot see yours. This is enforced by the server, not merely hidden on screen.

**You are never given a project from your own team.** The assignment step checks this
automatically.

**Being a tough marker will not hurt anyone.** After scoring finishes, HackFlow compares each
judge against their own average and adjusts for it. A consistently strict judge does not drag
their projects down the rankings, and a generous one does not lift theirs up. So score the
way that feels honest to you. You do not need to guess what the other judges are doing.

*(If you want the mathematics behind that, it is written up in `JUDGING.md`.)*

---

## 7. For organizers: running the event

### Step 1: Create the event

Choose **Create event**.

![The create-event form](docs/screenshots/manual/17-create-event.png)

You give it a name, a web address slug, a description, start and end dates, the themes teams
may enter under, the prizes, and the largest team you will allow. Only the name, slug, and
dates are required. Everything else can be added later.

**New events start as drafts**, visible only to organizers, so you can set everything up
before anyone sees it. (To restore an event from a backup file instead, use **Import an
event** on the **Events** page.)

### Step 2: Settings, and going live

From the event page, choose **Event settings**.

![The event settings screen](docs/screenshots/manual/11-event-settings.png)

- **Visibility**: **Publish event** makes it visible so participants can find and join it.
  **Move back to draft** hides it again.
- **Dates**: move the start or the submission deadline. **Close submissions now** ends the
  submission window immediately, which is also what opens judging.
- **Rules**: plain text shown on the event page.
- Further down: the maximum team size, tracks, the prize list, and a downloadable backup of
  the whole event.
- **Embed on your site**: a snippet of code you paste into your own website to show this
  event's projects there. It updates itself as teams submit, and shows winners only after
  your results reveal. **Preview the widget** opens it on its own.

Raising or lowering the team-size limit only affects **new** joins. A team that is already
larger than a reduced limit is left alone rather than having someone thrown out.

### Step 3: Write the scorecard

From the event page, choose **Judging rubric**.

![The rubric builder](docs/screenshots/manual/12-rubric-builder.png)

A scorecard is a list of things judges mark on, each with a weight, a maximum and an
optional description. The weights must add up to 100%, and the page tells you live whether
they do, so you cannot save something that does not add up.

You can create more than one scorecard for an event (for example *Technical* and
*Presentation*), and judges get them combined into one form.

**Scorecards lock once scoring starts.** As soon as the first judge submits a score, the
scorecard can no longer be edited. This guarantees every project in the event was measured
against the same thing.

### Step 4: Tell everyone something

The **Announcements** card on the event page is how you reach participants once the event is
running: a moved deadline, a demo schedule, a room change.

![Posting an announcement](docs/screenshots/manual/21-announcements.png)

Write a title and a message and choose **Post announcement**. It appears on the event page
and on the dashboard of everyone on a team in the event, and **Delete** takes it down again.
It is plain text. If email is set up you can also email it to participants, and if the event
has a notification address (see *Optional* below) it is posted there too, which is handy for a
Discord or Slack channel.

### Step 5: Judges and the work

From the event page, choose **Assignments & results**.

![The assignments and results screen](docs/screenshots/manual/13-assignments-results.png)

**To bring in judges**, use the *Judges* card further down: fill in the small form and
choose **Create invitation**. You get a link to send them. You can set how long it stays
valid and note who it was for.

**To hand out the judging**, choose **Assign judges**. HackFlow gives each submitted project
three judges from this event's panel, spreads the work evenly, and never gives anyone a
project from their own team or one they declared a conflict with. Running it again only
fills gaps. It will not duplicate work anyone already has. Assignment opens once
submissions close.

**Judges should finish by** sets a judging deadline. Judges see it on their list with a
countdown, reminder emails mention it, and the progress card below marks anyone still
behind as **Overdue**. It never locks scoring: a late score still counts.

**Eligibility** lists every submitted project. **Disqualify** takes one out of the
competition: you give a reason, which the team sees, and the project leaves the gallery,
voting, judging, the standings and the winners list. Scores already given are kept, so
**Reinstate** puts it back exactly as it was. Every ruling is recorded with your name.

**Judging progress** shows who has scored what:

![The judging progress card](docs/screenshots/manual/22-judging-progress.png)

- Each judge's **scored / assigned** count, and when they last scored.
- **Remove** takes someone who dropped out off the panel; their unscored projects go back
  into the pool for the next **Assign judges** run.
- **Add an existing judge** puts someone who already judges on HackFlow onto this event's
  panel. New judges need an invitation.
- If email is set up, **Remind** nudges a judge who is behind.

### Step 6: Voting and results

The same screen controls the public side:

![The community voting card](docs/screenshots/manual/24-community-voting.png)

- **Open voting** or **Close voting** at any time.
- **Who can vote**:
  - *Signed-in accounts* (the default): anyone with a HackFlow account.
  - *Anyone who confirms an email*: guests enter an address and get a link; one vote per
    project per address, whether they vote as a guest or signed in. Needs email set up.
  - *Anyone with the link*: no sign-up at all. The easiest for a big public audience, and
    the easiest to game: someone determined can vote more than once from different
    networks. Keep the community prize small if you use it.
- **Stop one person voting from several accounts** (both optional, both off at first):
  - *Require a verified email to vote*: each voter must prove their address from their
    profile, so every extra account needs an inbox of its own. Needs email set up.
  - *Only accounts created before*: accounts made after this moment can't vote, so nobody
    can create a pile of accounts once they see who is winning. Works without email.
- **Suspicious votes** appears when several different voters voted from the same device
  and network. That can be a shared lab computer, so look before you act. **Void**
  removes one vote from the count and records it in the audit log.
- **Hide vote counts until** sets the moment results become public. Until then, nobody
  outside the organizing team can see counts or standings.
- **Exports** gives you a spreadsheet of participants, projects, assignments, raw scores, or
  final normalized standings, at any point during the event.

### Step 7: Pick the winners

![The winners card](docs/screenshots/manual/23-winners.png)

Each prize comes with a **suggestion** from the standings: overall prizes in rank order, a
track prize from that track's best entry. Choose **Use suggestion** or pick another project.
Nobody sees the winners until your results reveal time.

### Helping someone sign in

When a participant or judge is locked out and the email reset isn't working for them, use
**Dashboard → Help someone sign in**:

![The help someone sign in card](docs/screenshots/manual/25-help-someone-sign-in.png)

Type their email, choose **Create reset link**, then **Copy link**, and send it to them
directly. The link is shown only once, works once, and expires after an hour. Organizers can
reset participants and judges; resetting another organizer takes an admin. Every link is
recorded with your name on it.

### Optional: notifications to other systems

Further down the **Event settings** screen you can give HackFlow a web address to notify when
something happens: a project is submitted, judging is assigned, a score arrives, an
announcement is posted, or results go live. It is useful for feeding a Discord or Slack
channel.

Each notification is cryptographically signed, so the system receiving it can confirm it
genuinely came from your HackFlow and was not altered on the way. This is entirely optional.
Leave it empty and HackFlow never contacts anything outside itself.

---

## 8. For admins: running the site

Admins get everything organizers have, plus a **Users** tab.

![The users screen](docs/screenshots/manual/26-admin-users.png)

- **Search** by name or email, or filter by role.
- **Change a role** from the drop-down on any account, for example to make an existing
  participant an organizer.
- **Deactivate** an account to sign it out everywhere and stop it logging in, without
  deleting anything it wrote. **Reactivate** undoes it.
- **Invite an organizer** creates a single-use link for someone who does not have an account
  yet.

The admin **Dashboard** also has an **Email delivery** card. Email is optional and off by
default (see the README's "Email (optional)" section). Once it is set up, press **Send test
email** to check it works before anyone needs a reset link.

---

## 9. Troubleshooting

**The page says my deadline has passed but I am not finished.**
Deadlines are enforced by the server and cannot be worked around from the browser. Ask your
organizer. They can move the event's end date from **Event settings**.

**My invite link does not work.**
The page will tell you why: the team is already full, the link has been replaced with a new
one, or you are already on that team (or on another team in the same hackathon; leave that
one first).

**I cannot see vote counts or rankings.**
That is intended until the organizer's reveal time. The numbers are genuinely withheld, not
just hidden from view, so refreshing or trying another browser will not reveal them early.

**I cannot vote.**
Check the event's voting is open. If the page says *Log in to vote*, this event only lets
accounts vote. If it says *Confirm your email to vote*, use the **Vote without an account**
box and open the emailed link in the same browser.

**I am a judge but I cannot see a project I want to score.**
You can only score what you were assigned. If you believe something is missing, ask the
organizer to re-run assignment.

**I'm a judge and my list is empty.**
Judging opens once an event's submissions close. The **Coming up** card on your Judging page
says when that is for each of your events.

**The scorecard will not save.**
The weights must total exactly 100%. The page shows the running total as you type. If it is
locked instead, scoring has already begun and it can no longer be changed.

**My new event doesn't show up for participants.**
New events start as drafts. Open **Event settings → Publish event**.

**Email-confirmed voting can't be selected.**
It needs email set up first; otherwise guests could never receive their link.

**I'm the admin, and I'm locked out.**
Anyone with access to the server can run:

```bash
docker compose exec api python -m app.auth.reset_link you@example.com
```

It prints a one-time reset link for that account. On Render, run
`python -m app.auth.reset_link you@example.com` from the service's **Shell** tab instead
(the Shell tab needs a paid plan).

**I want to start over with clean sample data.**
Stop the site and run:

```bash
docker compose down -v
docker compose up
```

This erases everything and re-creates the original sample data. Do not run it on a real
event, because it deletes real entries too.

---

## Where to go next

This manual covers using HackFlow. If you want to understand or modify how it works:

- **`README.md`**: what it is and how to run it
- **`ARCHITECTURE.md`**: how the system is put together
- **`DATA-MODEL.md`**: what is stored, and how to get data in and out
- **`JUDGING.md`**: the assignment algorithm and the normalization mathematics
- **`THREAT-MODEL.md`**: the abuse scenarios it defends against, and how
