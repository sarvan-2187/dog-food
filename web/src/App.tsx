import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { RequireAuth } from './components/auth/guards';
import { NavBar } from './components/layout/NavBar';
import { AuthProvider } from './lib/auth-context';
import { EventCreatePage } from './pages/EventCreatePage';
import { EventDetailPage } from './pages/EventDetailPage';
import { EventResultsPage } from './pages/EventResultsPage';
import { EventSettingsPage } from './pages/EventSettingsPage';
import { EventsPage } from './pages/EventsPage';
import { GalleryPage } from './pages/GalleryPage';
import { JoinTeamPage } from './pages/JoinTeamPage';
import { JudgeDashboardPage } from './pages/JudgeDashboardPage';
import { JudgeInvitePage } from './pages/JudgeInvitePage';
import { LandingPage } from './pages/LandingPage';
import { LoginPage } from './pages/LoginPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { ProfilePage } from './pages/ProfilePage';
import { RegisterPage } from './pages/RegisterPage';
import { RubricBuilderPage } from './pages/RubricBuilderPage';
import { ScorePage } from './pages/ScorePage';
import { SubmissionDetailPage } from './pages/SubmissionDetailPage';
import { SubmissionPage } from './pages/SubmissionPage';
import { TeamsMinePage } from './pages/TeamsMinePage';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="min-h-screen">
          <NavBar />
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/events/new" element={<EventCreatePage />} />
            <Route path="/events/:slug" element={<EventDetailPage />} />
            <Route path="/events/:slug/rubric" element={<RubricBuilderPage />} />
            <Route path="/events/:slug/settings" element={<EventSettingsPage />} />
            <Route path="/events/:slug/results" element={<EventResultsPage />} />
            <Route path="/events/:slug/gallery" element={<GalleryPage />} />
            <Route path="/judge" element={<JudgeDashboardPage />} />
            <Route path="/judge-invite/:token" element={<JudgeInvitePage />} />
            <Route path="/assignments/:assignmentId/score" element={<ScorePage />} />
            <Route path="/gallery" element={<GalleryPage />} />
            <Route path="/submissions/:submissionId" element={<SubmissionDetailPage />} />
            <Route path="/join/:code" element={<JoinTeamPage />} />
            <Route
              path="/profile"
              element={
                <RequireAuth>
                  <ProfilePage />
                </RequireAuth>
              }
            />
            <Route
              path="/teams/mine"
              element={
                <RequireAuth>
                  <TeamsMinePage />
                </RequireAuth>
              }
            />
            <Route
              path="/teams/:teamId/submission"
              element={
                <RequireAuth>
                  <SubmissionPage />
                </RequireAuth>
              }
            />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}
