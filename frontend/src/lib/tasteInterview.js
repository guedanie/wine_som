// The Somm's taste-profile interview — a short, scripted conversational Q&A.
// Each question renders as a Somm bubble + answer chips; answers build a
// structured taste_profile that feeds recommendations.
export const TASTE_QUESTIONS = [
  {
    id: 'lean',
    prompt: "Let's talk palate. First, the big one — what pulls you in?",
    multi: false,
    options: [
      { label: 'Bold reds', value: 'bold_red' },
      { label: 'Elegant reds', value: 'elegant_red' },
      { label: 'Crisp whites', value: 'crisp_white' },
      { label: 'Rich whites', value: 'rich_white' },
      { label: 'Rosé & bubbles', value: 'rose_sparkling' },
      { label: 'A bit of everything', value: 'everything' },
    ],
  },
  {
    id: 'body',
    prompt: 'And when it comes to weight in the glass?',
    multi: false,
    options: [
      { label: 'Light & bright', value: 'light' },
      { label: 'Medium & balanced', value: 'medium' },
      { label: 'Big & bold', value: 'full' },
    ],
  },
  {
    id: 'sweetness',
    prompt: 'How do you feel about sweetness?',
    multi: false,
    options: [
      { label: 'Bone dry, always', value: 'dry' },
      { label: 'Dry, but a touch is fine', value: 'offdry' },
      { label: 'I like them sweeter', value: 'sweet' },
    ],
  },
  {
    id: 'adventurous',
    prompt: "When I pour you something, are you…",
    multi: false,
    options: [
      { label: 'Loyal to what I love', value: 'loyal' },
      { label: 'Open to a nudge', value: 'open' },
      { label: 'Surprise me', value: 'surprise' },
    ],
  },
  {
    id: 'regions_love',
    prompt: 'Any regions you gravitate toward? (pick any)',
    multi: true,
    allowFree: true,
    options: [
      { label: 'Napa' }, { label: 'Bordeaux' }, { label: 'Tuscany' },
      { label: 'Rhône' }, { label: 'Rioja' }, { label: 'Willamette' },
      { label: 'No strong preference' },
    ],
  },
  {
    id: 'avoid',
    prompt: 'Last one — anything you steer clear of?',
    multi: true,
    allowFree: true,
    options: [
      { label: 'Oaky Chardonnay' }, { label: 'High tannins' },
      { label: 'Sweet wines' }, { label: 'Very high alcohol' },
      { label: 'Nothing, really' },
    ],
  },
];

// answers: { [questionId]: value | value[] } → a clean structured profile.
export function buildProfile(answers) {
  const val = a => (Array.isArray(a) ? a : a != null ? [a] : []);
  const clean = list => list.filter(v => v && !/^no strong|^nothing/i.test(v));
  return {
    lean: answers.lean ?? null,
    body: answers.body ?? null,
    sweetness: answers.sweetness ?? null,
    adventurous: answers.adventurous ?? null,
    regions_love: clean(val(answers.regions_love)),
    avoid: clean(val(answers.avoid)),
    completed_at: new Date().toISOString(),
  };
}
