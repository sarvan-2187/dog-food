import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { RequireAuth } from './components/auth/guards';
import { NavBar } from './components/layout/NavBar';
import { AuthProvider } from './lib/auth-context';
import { EventCreatePage } from './pages/EventCreatePage';
import { EventDetailPage } from './pages/EventDetailPage';
import { EventsPage } from './pages/EventsPage';
import { GalleryPage } from './pages/GalleryPage';
import { JoinTeamPage } from './pages/JoinTeamPage';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { SubmissionPage } from './pages/SubmissionPage';
import { TeamsMinePage } from './pages/TeamsMinePage';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="min-h-screen">
          <NavBar />
          <Routes>
            <Route path="/" element={<Navigate to="/events" replace />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/events/new" element={<EventCreatePage />} />
            <Route path="/events/:slug" element={<EventDetailPage />} />
            <Route path="/gallery" element={<GalleryPage />} />
            <Route path="/join/:code" element={<JoinTeamPage />} />
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
          </Routes>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}
