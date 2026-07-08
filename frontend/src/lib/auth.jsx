// Auth + favorites context. Optional accounts, anonymous-first: with no session
// the app is fully usable and useAuth() returns an anonymous stub. The provider
// centralizes session, saved bottles, and the sign-in prompt so components just
// call useAuth().toggleSave(wine) / isSaved(id) / requireSignIn().
import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { supabase, isAuthConfigured } from './supabase.js';
import { setPendingSave, getPendingSave, clearPendingSave } from './pendingSave.js';
import { listFavoriteIds, addFavorite, removeFavorite } from './favorites.js';
import SignInModal from '../components/SignInModal.jsx';

const AuthContext = createContext(null);

const ANON = {
  authState: 'anonymous', user: null, ready: true, isConfigured: false, savedIds: [],
  isSaved: () => false, toggleSave: () => {}, requireSignIn: () => {}, signOut: () => {},
  signInWithEmail: async () => ({ error: new Error('auth not configured') }),
};

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [ready, setReady]     = useState(!isAuthConfigured());
  const [savedIds, setSavedIds] = useState([]);
  const [prompt, setPrompt]   = useState(null);   // { wine } while the sign-in modal is open

  const user = session?.user ?? null;

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setReady(true); });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  // Load favorites on sign-in, and apply any pending save from the round-trip.
  useEffect(() => {
    if (!user) { setSavedIds([]); return; }
    let alive = true;
    (async () => {
      const ids = await listFavoriteIds(user.id);
      const pending = getPendingSave();
      if (pending?.wine_id && !ids.includes(pending.wine_id)) {
        if (await addFavorite(user.id, pending.wine_id)) ids.push(pending.wine_id);
      }
      clearPendingSave();
      if (alive) { setSavedIds(ids); setPrompt(null); }
    })();
    return () => { alive = false; };
  }, [user]);

  const isSaved = useCallback(id => savedIds.includes(id), [savedIds]);
  const requireSignIn = useCallback((wine = null) => setPrompt({ wine }), []);
  const signInWithEmail = useCallback(
    email => supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: window.location.origin } }),
    [],
  );
  const signOut = useCallback(() => supabase?.auth.signOut(), []);

  const toggleSave = useCallback(async (wine) => {
    const id = wine.wine_id ?? wine.id;
    if (!id) return;
    if (!user) {                                   // anon → stash intent + prompt sign-in
      setPendingSave({ wine_id: id, name: wine.name });
      requireSignIn(wine);
      return;
    }
    if (savedIds.includes(id)) {                    // optimistic remove
      setSavedIds(prev => prev.filter(x => x !== id));
      if (!(await removeFavorite(user.id, id))) setSavedIds(prev => [...prev, id]);
    } else {                                        // optimistic add
      setSavedIds(prev => [...prev, id]);
      if (!(await addFavorite(user.id, id))) setSavedIds(prev => prev.filter(x => x !== id));
    }
  }, [user, savedIds, requireSignIn]);

  const value = {
    authState: user ? 'signed_in' : 'anonymous',
    user, ready, savedIds, isConfigured: isAuthConfigured(),
    isSaved, toggleSave, requireSignIn, signInWithEmail, signOut,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
      {prompt && (
        <SignInModal wine={prompt.wine} onClose={() => setPrompt(null)} signInWithEmail={signInWithEmail} />
      )}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext) ?? ANON;
}
