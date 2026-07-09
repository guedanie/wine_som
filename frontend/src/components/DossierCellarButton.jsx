import { useState } from 'react';
import { useAuth } from '../lib/auth.jsx';
import Btn from './Btn.jsx';
import AddBottleModal from './AddBottleModal.jsx';

// "Add to cellar" on the dossier — opens the Add-bottle form prefilled from the
// catalog wine. Anonymous tap opens the sign-in prompt. Hidden if auth isn't
// configured or there's no wine id.
export default function DossierCellarButton({ wine, style }) {
  const { isConfigured, authState, user, requireSignIn } = useAuth();
  const [open, setOpen] = useState(false);
  if (!isConfigured || !wine?.id) return null;

  const prefill = {
    wine_id: wine.id,
    name: wine.name,
    vintage: wine.vintage_year ?? wine.vintage ?? null,
    region: wine.region ?? null,
    varietal: wine.varietal ?? null,
    wine_type: wine.wine_type ?? 'red',
  };

  const onClick = () => (authState === 'signed_in' ? setOpen(true) : requireSignIn());

  return (
    <>
      <Btn variant="ghost" onClick={onClick} style={style}>Add to cellar</Btn>
      {open && (
        <AddBottleModal userId={user.id} prefill={prefill}
          onClose={() => setOpen(false)} onAdded={() => setOpen(false)} />
      )}
    </>
  );
}
