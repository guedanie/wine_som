# Terroir — Wine App UI Kit

A clickable, high-fidelity recreation of the wine‑recommendation app's core
screens, built on the Terroir design system. It's a **prototype**, not production
code — components are cosmetic and the data is fake (`data.jsx`).

## Run it
Open `index.html`. It loads React + Babel from CDN and the design tokens from
`../../colors_and_type.css`. No build step.

## Flow (click‑through)
1. **Preference capture** (`PreferenceCapture.jsx`) — zip, budget, taste cards,
   occasion → *Find wines*.
2. **Recommendations** (`ChatRecommend.jsx`) — split view: sommelier conversation
   on the left, framed wine cards on the right. Click any card to open it.
3. **Wine dossier** (`RegionDossier.jsx`) — the wine framed by its region poster:
   tasting note, structure bars, local availability, "more from this region."
4. **Discover** (`Discovery.jsx`) — browse regions as travel posters; click one to
   jump into its wines.

Navigate anytime via the top nav (Recommend / Discover) or the wordmark (home).

## Files
| File | Role |
|---|---|
| `index.html` | App shell + nav + screen routing |
| `shared.jsx` | Primitives: `Stamp`, `Contours`, `Tag`, `Btn`, `WineCard`, `Poster`, `StructureBars` |
| `data.jsx` | Sample `REGIONS` and `WINES` |
| `PreferenceCapture.jsx` · `ChatRecommend.jsx` · `RegionDossier.jsx` · `Discovery.jsx` | The four screens |

## Notes
- The **contour map** motif is generated procedurally in `shared.jsx` (`Contours`)
  — each wine seeds a slightly different map.
- Region **posters** are live for Tuscany (`poster-tuscany.png`) and Paso Robles
  (`poster-paso-robles.png`); Mendoza and Willamette fall back to the striped
  placeholder until posters are generated per the art‑direction spec in the root
  `CLAUDE.md`.
- The **contour map** is NOT used on wine cards (kept clean) — it appears on the
  dossier page only (section divider + store markers).
- Components share scope via `window` (each Babel script is its own module), so
  every component ends with `Object.assign(window, { … })`.
