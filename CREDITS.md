# Image credits

The photographs bundled under `web/public/images/` are real hackathon
photographs, not stock illustration. Every one was retrieved through
[Openverse](https://openverse.org) filtered to licences that permit commercial
use, and each is listed below with its creator, its source page, and its
licence.

Several are **CC BY-SA**, which is a share-alike licence: if you crop, recolour
or otherwise adapt one of those images, the adapted image has to be released
under the same licence. The images are used unmodified apart from resizing and,
for the event covers, a centre crop to 16:9. Several seeded events share a cover (the
"Raptor Judging Showcase" demo event reuses `cover-devtools.jpg`); no new photographs
were added after this table was written.

If you are replacing these with your own event photography, delete the files and
this table together — an attribution list that no longer matches what ships is
worse than none.

| File | Source | Creator | Licence |
|---|---|---|---|
| `images/community/hero-hack-room.jpg` | [hackNY Spring 2011 Student Hackathon](https://www.flickr.com/photos/61623410@N08/5605012373) | hackNY | BY-SA 2.0 |
| `images/community/wide-room.jpg` | [Spring 2012 hackNY Student Hackathon Coding](https://www.flickr.com/photos/61623410@N08/6890224676) | hackNY | BY-SA 2.0 |
| `images/community/chalkboard-huddle.jpg` | [Fall 2010 hackNY Student Hackathon](https://www.flickr.com/photos/61623410@N08/5685034971) | hackNY | BY-SA 2.0 |
| `images/community/team-laptops.jpg` | [Fall 2010 hackNY Student Hackathon](https://www.flickr.com/photos/61623410@N08/5685366097) | hackNY | BY-SA 2.0 |
| `images/community/build-table.jpg` | [Wikimedia Hackathon event in Catania in 2024 5](https://commons.wikimedia.org/w/index.php?curid=147860808) | Pierpao | CC0 1.0 |
| `images/community/demo-stage.jpg` | [spring 2012 hackNY student hackathon presentations](https://www.flickr.com/photos/61623410@N08/6893162478) | hackNY | BY-SA 2.0 |
| `images/community/panel-talk.jpg` | [Whatever happened to journalism? (Day 2)](https://www.flickr.com/photos/92582247@N08/11277851943) | Berliner.Gazette | BY 2.0 |
| `images/community/group-photo.jpg` | [Hackathon team](https://www.flickr.com/photos/19451080@N00/12850944674) | Phillie Casablanca | BY 2.0 |
| `images/community/opening-hall.jpg` | [Hackathon, Workshop & Edit-a-thon at WikiConference India 2016](https://commons.wikimedia.org/w/index.php?curid=50502428) | Hasive | BY-SA 3.0 |
| `images/community/winners-lineup.jpg` | [Hackathon winners and developers of 'Edifice' present their work to Google and receive their prize](https://www.flickr.com/photos/29965049@N00/8148594868) | Center for Neighborhood Technology | BY-SA 2.0 |
| `images/community/pair-building.jpg` | [Fall 2011 Student Hackathon Coding](https://www.flickr.com/photos/61623410@N08/6203294048) | hackNY | BY-SA 2.0 |
| `images/community/certificate-team.jpg` | [spring 2012 hackNY student hackathon presentations](https://www.flickr.com/photos/61623410@N08/6893188940) | hackNY | BY-SA 2.0 |
| `images/covers/cover-ai-agents.jpg` | [Fall 2011 Student Hackathon Coding](https://www.flickr.com/photos/61623410@N08/6203299638) | hackNY | BY-SA 2.0 |
| `images/covers/cover-devtools.jpg` | [Fall 2011 Student Hackathon Coding](https://www.flickr.com/photos/61623410@N08/6202775045) | hackNY | BY-SA 2.0 |
| `images/covers/cover-climate.jpg` | [Whatever happened to journalism? (Day 2)](https://www.flickr.com/photos/92582247@N08/11277851943) | Berliner.Gazette | BY 2.0 |
| `images/covers/cover-women-in-tech.jpg` | [Wikimedia Hackathon 2020 hackathon team members](https://commons.wikimedia.org/w/index.php?curid=81128830) | Andis Rado | BY-SA 4.0 |
| `images/covers/cover-fintech.jpg` | [spring 2012 hackNY student hackathon presentations](https://www.flickr.com/photos/61623410@N08/6893162478) | hackNY | BY-SA 2.0 |
| `images/covers/cover-open-track.jpg` | [Wikimedia hackathon team - Open Minds Awards 2017](https://commons.wikimedia.org/w/index.php?curid=62810611) | Jean-Frédéric | CC0 1.0 |
| `images/covers/cover-campus-48h.jpg` | [Hackathon, Workshop & Edit-a-thon at WikiConference India 2016](https://commons.wikimedia.org/w/index.php?curid=50502428) | Hasive | BY-SA 3.0 |
| `images/covers/cover-quantum.jpg` | [Fall 2010 hackNY Student Hackathon](https://www.flickr.com/photos/61623410@N08/5685366097) | hackNY | BY-SA 2.0 |

Machine-readable form of the same data: `web/public/images/attribution.json`.

The HackFlow raptor mark (`web/public/logo.png`, and `web/public/images/raptor.png`
derived from it by trimming and removing a faint watermark from the alpha
channel) is the project's own asset and is not covered by the table above.

# Software

Everything the running app depends on is pinned in `api/requirements.txt` and
`web/package.json` (with `package-lock.json`) and installed at build time; each package
keeps its own licence. Two are worth naming because they're easy to miss:

| Component | Used for | Licence |
|---|---|---|
| [driver.js](https://driverjs.com) | The guided tour, bundled into the app (no network calls) | MIT |
| [Mailpit](https://mailpit.axllent.org) (`axllent/mailpit:v1.31.1`) | *Optional* local test inbox for password-reset email, started only by `docker-compose.mail.yml`. Not part of the default stack | MIT |

# Contributors

Built by Team CodeHawk. The commits in this repository are by Sarvan Kumar
([@sarvan-2187](https://github.com/sarvan-2187)) and
[@pranavneelu06](https://github.com/pranavneelu06), who independently built the first
version of Phase 10.1, 10.2 and 10.4 and fixed the login/register `banner` landmark.
Commits co-written with Claude (Anthropic) carry a `Co-Authored-By` trailer.
