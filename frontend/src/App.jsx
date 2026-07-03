import { Routes, Route } from 'react-router-dom';
import NavBar from './components/NavBar.jsx';
import PreferenceCapture from './screens/PreferenceCapture.jsx';
import ChatRecommend from './screens/ChatRecommend.jsx';
import RegionDossier from './screens/RegionDossier.jsx';
import Discovery from './screens/Discovery.jsx';
import RegionBrowse from './screens/RegionBrowse.jsx';
import RegionDetail from './screens/RegionDetail.jsx';
import SearchScreen from './screens/SearchScreen.jsx';

export default function App() {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--cream)' }}>
      <NavBar />
      <Routes>
        <Route path="/" element={<PreferenceCapture />} />
        <Route path="/recommend" element={<ChatRecommend />} />
        <Route path="/wine/:id" element={<RegionDossier />} />
        <Route path="/discover" element={<Discovery />} />
        <Route path="/region/:slug" element={<RegionBrowse />} />
        <Route path="/regions/:slug" element={<RegionDetail />} />
        <Route path="/search" element={<SearchScreen />} />
      </Routes>
    </div>
  );
}
