import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import type { Role } from '../types';

/**
 * The post-login guided tour (PLAN.md Phase 8).
 *
 * Steps are a per-role *superset*: every step names a selector, and the ones
 * whose element isn't on the current page are dropped before the tour starts.
 * That's what lets one definition run from any screen without choreographing
 * navigation between steps -- the tour gets richer where more anchors happen
 * to be present, rather than breaking when they aren't. Steps with no selector
 * are centered modals and always survive the filter.
 */
export interface TourStep {
  selector?: string;
  title: string;
  description: string;
}

const INTRO: TourStep = {
  title: 'Welcome to HackFlow',
  description:
    'This is a 60-second look around. You can leave any time by pressing Escape, and replay it later from your Profile page.',
};

const OUTRO: TourStep = {
  title: "That's the whole tour",
  description:
    'You can run it again whenever you like — open <b>Profile</b> and choose <b>Replay the guided tour</b>.',
};

const PARTICIPANT: TourStep[] = [
  INTRO,
  {
    selector: '[data-tour="nav-events"]',
    title: 'Step 1 — Find your hackathon',
    description:
      'Everything starts here. <b>Events</b> lists every hackathon on this site. Open the one you signed up for to see its dates, its themes, and the deadline you need to beat.',
  },
  {
    selector: '[data-tour="event-list"]',
    title: 'Pick one to open it',
    description:
      'Each card is one hackathon. Click it to see the full details and to create or join a team.',
  },
  {
    selector: '[data-tour="nav-teams"]',
    title: 'Step 2 — Get on a team',
    description:
      'You submit as a team, not as an individual. Either create a team and share the invite link with your teammates, or paste the link someone already sent you. Teams can hold up to four people.',
  },
  {
    title: 'Step 3 — Write your project up',
    description:
      'Once you are on a team you get one project page. It <b>saves as you type</b> — there is no Save button to forget. The deadline counts down at the top of that page, and the site stops accepting edits the moment it runs out, so do not leave it to the final minute.',
  },
  {
    selector: '[data-tour="nav-gallery"]',
    title: 'Step 4 — See everyone else',
    description:
      'The <b>Gallery</b> shows every submitted project. Depending on how the organizer set things up, you may also be able to vote and leave comments here. Scores and standings stay hidden until the organizer reveals them, so early votes cannot sway the crowd.',
  },
  {
    selector: '[data-tour="nav-profile"]',
    title: 'Your account',
    description:
      'Your name, your photo, and the log-out button live here — along with the button that replays this tour.',
  },
  OUTRO,
];

const JUDGE: TourStep[] = [
  INTRO,
  {
    selector: '[data-tour="nav-judge"]',
    title: 'Step 1 — Your judging list',
    description:
      '<b>Judging</b> is your home base. It lists only the projects assigned to you, and shows how many you have finished versus how many are left.',
  },
  {
    title: 'Step 2 — How scoring works',
    description:
      'Each project opens a score form built from the rubric the organizer wrote. Every criterion carries a weight, so the form does the arithmetic for you — you just judge each one honestly.',
  },
  {
    title: 'You are judging alone, on purpose',
    description:
      "You cannot see any other judge's scores or comments, and they cannot see yours. You are also never assigned a project from a team you belong to. Both rules are enforced by the server, not just hidden on screen.",
  },
  {
    title: 'Being a tough marker will not hurt anyone',
    description:
      'After scoring closes, the site compares each judge against their own average and adjusts accordingly. A consistently strict judge does not drag their projects down, and a generous one does not lift theirs up. Score the way that feels right to you.',
  },
  {
    selector: '[data-tour="nav-gallery"]',
    title: 'Browsing everything else',
    description:
      'The <b>Gallery</b> shows all submitted projects, including ones not assigned to you. Looking is fine — you simply cannot score outside your own list.',
  },
  {
    selector: '[data-tour="nav-profile"]',
    title: 'Your account',
    description: 'Your details, your photo, log out, and the button to replay this tour.',
  },
  OUTRO,
];

// PLAN.md Phase 9.4: shown on the dashboard, where the card lives.
const HELP_SIGN_IN: TourStep = {
  selector: '[data-tour="help-sign-in"]',
  title: "When someone can't sign in",
  description:
    "If a participant or judge is locked out and the email reset isn't an option, type their email here to get a one-time reset link to send them. It works once, for an hour.",
};

const ORGANIZER: TourStep[] = [
  INTRO,
  {
    selector: '[data-tour="nav-events"]',
    title: 'Step 1 — Your events',
    description:
      'Every hackathon you run shows up under <b>Events</b>. Open one to reach its controls.',
  },
  {
    selector: '[data-tour="nav-create-event"]',
    title: 'Step 2 — Create a hackathon',
    description:
      'Give it a name, a start and end date, the themes teams can enter under, the prizes on offer, and the biggest team you will allow. All of it can be changed later.',
  },
  {
    title: 'Step 3 — Write the scorecard',
    description:
      'Each event gets one or more rubrics — the list of things judges mark on, each with a weight. The weights have to add up to 100%, and the page tells you live whether they do. Once the first judge submits a score the rubric locks, so nobody is scored against shifting goalposts.',
  },
  {
    title: 'Step 4 — Bring in judges and hand out the work',
    description:
      'Invite judges with a link, then press the assignment button once submissions close. The site spreads projects evenly across your judges and automatically avoids giving anyone a project from their own team.',
  },
  {
    title: 'Step 5 — Results, on your schedule',
    description:
      'Standings stay hidden until the reveal time you set. You can watch judging progress the whole way through, and export any of it — projects, judges, raw scores, final rankings — as a spreadsheet at any point.',
  },
  {
    title: 'Plumbing, if you want it',
    description:
      "Each event's settings page can also post a signed notification to a web address of yours whenever something happens — a project is submitted, judging is assigned, a score lands, results go live. Useful for wiring HackFlow into a Discord or Slack channel. Entirely optional.",
  },
  HELP_SIGN_IN,
  {
    selector: '[data-tour="nav-profile"]',
    title: 'Your account',
    description: 'Your details, log out, and the button to replay this tour.',
  },
  OUTRO,
];

// Admins get the organizer tour plus the one card only they can see.
const ADMIN: TourStep[] = [
  ...ORGANIZER.slice(0, ORGANIZER.indexOf(HELP_SIGN_IN) + 1),
  {
    selector: '[data-tour="email-delivery"]',
    title: 'Password reset emails',
    description:
      'Off by default, so HackFlow makes no outbound connections. Point it at your own mail server and people who forget their password can reset it themselves by email. <b>Send test email</b> confirms the settings work before anyone needs them.',
  },
  ...ORGANIZER.slice(ORGANIZER.indexOf(HELP_SIGN_IN) + 1),
];

const TOURS: Record<Role, TourStep[]> = {
  participant: PARTICIPANT,
  judge: JUDGE,
  organizer: ORGANIZER,
  admin: ADMIN,
};

const seenKey = (role: Role) => `hackflow.tour.seen.${role}`;

/** Per-browser, per-role. Someone promoted from participant to judge should
 *  get the judge tour too, rather than one blanket "seen everything" flag. */
export function hasSeenTour(role: Role): boolean {
  try {
    return localStorage.getItem(seenKey(role)) === '1';
  } catch {
    // Private browsing / blocked storage: treat as unseen rather than crashing.
    return false;
  }
}

export function markTourSeen(role: Role): void {
  try {
    localStorage.setItem(seenKey(role), '1');
  } catch {
    // Nothing to do -- the tour simply offers itself again next time.
  }
}

/** Present *and* rendered. The desktop nav stays in the DOM at phone widths
 *  behind `hidden md:flex`, so a querySelector hit alone would have the tour
 *  spotlighting a zero-size box. On a phone the nav steps drop out and the
 *  plain-language modal steps carry the tour instead. */
function isVisible(selector: string): boolean {
  return (document.querySelector(selector)?.getClientRects().length ?? 0) > 0;
}

export function runTour(role: Role): void {
  const steps = TOURS[role].filter((s) => !s.selector || isVisible(s.selector));

  driver({
    showProgress: true,
    allowClose: true,
    overlayColor: '#1F2426',
    nextBtnText: 'Next',
    prevBtnText: 'Back',
    doneBtnText: 'Done',
    popoverClass: 'hackflow-tour',
    onDestroyed: () => markTourSeen(role),
    steps: steps.map((s) => ({
      element: s.selector,
      popover: { title: s.title, description: s.description },
    })),
  }).drive();
}
