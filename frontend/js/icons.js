// icons.js — pre-rendered SVG strings for JS-injected icon use.
// Uses Lucide icon paths (MIT license). All icons render at 1em x 1em so
// the parent element's font-size controls the display size.

const Icons = (() => {
  const base = (inner) =>
    `<svg xmlns="http://www.w3.org/2000/svg" class="icon" viewBox="0 0 24 24" fill="none" ` +
    `stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;

  return {
    flame:      base('<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>'),
    star:       base('<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>'),
    trendingUp: base('<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>'),
    sunrise:    base('<path d="M12 2v8"/><path d="m4.93 10.93 1.41 1.41"/><path d="M2 18h2"/><path d="M20 18h2"/><path d="m19.07 10.93-1.41 1.41"/><path d="M22 22H2"/><path d="m16 6-4 4-4-4"/><path d="M16 18a4 4 0 0 0-8 0"/>'),
    dumbbell:   base('<path d="m6.5 6.5 11 11"/><path d="m21 21-1-1"/><path d="m3 3 1 1"/><path d="m18 22 4-4"/><path d="m2 6 4-4"/><path d="m3 10 7-7"/><path d="m14 21 7-7"/>'),
    checkCircle:base('<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>'),
    sparkles:   base('<path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/>'),
    calendar:   base('<rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/>'),
    shuffle:    base('<path d="M2 18h1.4c1.3 0 2.5-.6 3.3-1.7l6.1-8.6c.7-1.1 2-1.7 3.3-1.7H22"/><path d="m18 2 4 4-4 4"/><path d="M2 6h1.9c1.5 0 2.9.9 3.6 2.2"/><path d="m18 22 4-4-4-4"/><path d="M21.8 16c-.7 1.6-2.2 2.7-3.8 2.7H16"/>'),
    refreshCw:  base('<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>'),
    rocket:     base('<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>'),
    lock:       base('<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>'),
    trophy:     base('<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2z"/>'),
    zap:        base('<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'),
    footprints: base('<path d="M4 16v-2.38C4 11.5 2.97 10.5 3 8c.03-2.72 1.49-6 4.5-6C9.37 2 10 3.8 10 5c0 4.1-4 4.9-4 8v3"/><path d="M12 16v-2.38c0-2.12-1.03-3.12-1-5.62.03-2.72 1.49-6 4.5-6 1.87 0 2.5 1.8 2.5 3 0 4.1-4 4.9-4 8v3"/><path d="M8 22a1 1 0 0 1-1-1v-1h2v1a1 1 0 0 1-1 1z"/><path d="M16 22a1 1 0 0 1-1-1v-1h2v1a1 1 0 0 1-1 1z"/>'),

    smile:      base('<circle cx="12" cy="12" r="10"/><path d="M8 13s1.5 2 4 2 4-2 4-2"/><line x1="9" x2="9.01" y1="9" y2="9"/><line x1="15" x2="15.01" y1="9" y2="9"/>'),
    briefcase:  base('<rect width="20" height="14" x="2" y="7" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>'),
    building2:  base('<path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/><path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/><path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/><path d="M10 6h4"/><path d="M10 10h4"/><path d="M10 14h4"/><path d="M10 18h4"/>'),
    route:      base('<circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/>'),
    trees:      base('<path d="M10 10v.2A3 3 0 0 1 8.9 16H5a3 3 0 0 1-1-5.8V10a3 3 0 0 1 6 0Z"/><path d="M7 16v6"/><path d="M13 19v3"/><path d="M12 19h8.5a3.5 3.5 0 0 0 0-7H18"/><path d="M18 12V9a3 3 0 0 0-6 0v3"/>'),

    // Custom runner figure (used for coach avatar and generation overlay)
    runner: `<svg xmlns="http://www.w3.org/2000/svg" class="icon" viewBox="0 0 40 40" fill="none">
      <defs><linearGradient id="icg" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#FF9040"/><stop offset="100%" stop-color="#E85500"/>
      </linearGradient></defs>
      <circle cx="27" cy="7" r="4" fill="url(#icg)"/>
      <line x1="26" y1="11" x2="19" y2="21" stroke="url(#icg)" stroke-width="3.5" stroke-linecap="round"/>
      <line x1="22.5" y1="15" x2="14" y2="11" stroke="url(#icg)" stroke-width="3" stroke-linecap="round"/>
      <line x1="22.5" y1="15" x2="30" y2="19" stroke="url(#icg)" stroke-width="3" stroke-linecap="round"/>
      <path d="M19 21 L12 28 L9 35" stroke="url(#icg)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M19 21 L25 28 L31 34" stroke="url(#icg)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,
  };
})();

// Map emoji characters from backend/legacy data to icon SVG strings
const achIconMap = {
  '👟': Icons.footprints,
  '🔟': Icons.trophy,
  '5️⃣0️⃣': Icons.trophy,
  '💯': Icons.trophy,
  '🥉': Icons.trophy,
  '🥈': Icons.trophy,
  '🥇': Icons.trophy,
  '🏆': Icons.trophy,
  '🔥': Icons.flame,
  '🔥🔥': Icons.flame,
  '⚡': Icons.zap,
  '💨': Icons.zap,
  '🗓️': Icons.calendar,
  '🔒': Icons.lock,
};

function achIconSvg(emojiOrName) {
  return achIconMap[emojiOrName] || Icons.star;
}
