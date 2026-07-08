import { useAuth } from '../lib/auth.jsx';
import Btn from './Btn.jsx';

// Labeled Save on the dossier: ghost "Save" → solid "Saved" when saved.
// Anonymous click opens the sign-in prompt (via toggleSave). Renders nothing if
// auth isn't configured or there's no wine id.
export default function DossierSaveButton({ wineId, name, style }) {
  const { isConfigured, isSaved, toggleSave } = useAuth();
  if (!isConfigured || !wineId) return null;
  const saved = isSaved(wineId);
  return (
    <Btn
      variant={saved ? 'primary' : 'ghost'}
      onClick={() => toggleSave({ wine_id: wineId, name })}
      style={style}
    >
      <svg width="12" height="16" viewBox="0 0 18 24" fill={saved ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" style={{ marginRight: 7 }}>
        <path d="M2 2h14v20l-7-5-7 5V2z" />
      </svg>
      {saved ? 'Saved' : 'Save'}
    </Btn>
  );
}
