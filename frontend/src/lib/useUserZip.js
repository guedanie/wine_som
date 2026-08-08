import { useLocation } from 'react-router-dom';
import { loadZip } from './useIsMobile.js';

/**
 * The single zip resolver. No screen should build its own chain.
 *
 * Every screen that filters inventory needs "where is the user?", and each one had
 * grown its own precedence chain from whatever navigation state its entry path
 * happened to carry. That produced two live bugs:
 *   - RegionDossier resolved `state.zip ?? chatState.prefs.zip ?? null`. ASK mode keeps
 *     its zip in `askZip` (lazy, asked in-conversation), so from the ask face the chain
 *     hit null, `getWine` dropped `?zip=`, and the API skipped its proximity filter —
 *     "available near you" listed 17 stores nationwide instead of 1, including a Spec's
 *     252 mi away. The header pill showed the right zip the whole time, because it read
 *     a DIFFERENT source.
 *   - RegionBrowse hard-coded '78209', so a Nashville user saw San Antonio inventory —
 *     wrong but plausible, which is harder to notice than an obviously over-broad list.
 *
 * Both were the same root cause: a new entry path not inheriting context the old one
 * carried. One chain, owned here, is what stops the next one.
 *
 * Returns a usable zip ALWAYS (never null) — a null silently disables server-side
 * proximity filtering, which fails open to the whole country.
 */
export function useUserZip() {
  const { state } = useLocation();
  const chat = state?.chatState ?? state?.pick?.chatState ?? null;
  return (
    state?.zip
    ?? state?._restored?.askZip
    ?? chat?.askZip
    ?? chat?.prefs?.zip
    ?? state?.prefs?.zip
    ?? loadZip()
  );
}
