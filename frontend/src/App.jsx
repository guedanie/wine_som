import { useEffect } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import { trackPageview } from './lib/analytics.js';
import NavBar from './components/NavBar.jsx';
import { TopBar, BottomTabs } from './components/MobileChrome.jsx';
import useIsMobile from './lib/useIsMobile.js';
import PreferenceCapture from './screens/PreferenceCapture.jsx';
import ChatRecommend from './screens/ChatRecommend.jsx';
import RegionDossier from './screens/RegionDossier.jsx';
import Discovery from './screens/Discovery.jsx';
import RegionBrowse from './screens/RegionBrowse.jsx';
import RegionDetail from './screens/RegionDetail.jsx';
import SearchScreen from './screens/SearchScreen.jsx';
import Saved from './screens/Saved.jsx';
import Account from './screens/Account.jsx';
import Cellar from './screens/Cellar.jsx';

function AppRoutes() {
  const { pathname } = useLocation();
  // SPA pageview on every route change (capture_pageview is off in init).
  useEffect(() => { trackPageview(pathname); }, [pathname]);
  return (
    <Routes>
      <Route path="/" element={<PreferenceCapture />} />
      <Route path="/recommend" element={<ChatRecommend />} />
      <Route path="/wine/:id" element={<RegionDossier />} />
      <Route path="/discover" element={<Discovery />} />
      <Route path="/region/:slug" element={<RegionBrowse />} />
      <Route path="/regions/:slug" element={<RegionDetail />} />
      <Route path="/search" element={<SearchScreen />} />
      <Route path="/saved" element={<Saved />} />
      <Route path="/account" element={<Account />} />
      <Route path="/cellar" element={<Cellar />} />
    </Routes>
  );
}

export default function App() {
  const isMobile = useIsMobile();

  if (isMobile) {
    return (
      <div style={{
        height: '100dvh', display: 'flex', flexDirection: 'column',
        background: 'var(--cream)', overflow: 'hidden',
      }}>
        <TopBar />
        <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
          <AppRoutes />
        </div>
        <BottomTabs />
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--cream)' }}>
      <NavBar />
      <AppRoutes />
    </div>
  );
}
