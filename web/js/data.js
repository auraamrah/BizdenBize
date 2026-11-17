// Fixed, language-independent constants. All words live in /locales/*.json.
export const LEVEL_ORDER = ['low', 'moderate', 'high', 'extreme'];
export const LEVEL_ICON = { low: '✓', moderate: '!', high: '▲', extreme: '‼' };
export const LEVEL_COLOR = { low: '#22c55e', moderate: '#eab308', high: '#f97316', extreme: '#ef4444' };
export const THRESHOLDS = [0.30, 0.55, 0.75]; // same cut-points as the backend model
export const SCORE_LABEL = { low: '< 0.30', moderate: '≥ 0.30', high: '≥ 0.55', extreme: '≥ 0.75' };
export const levelKey = score => score >= 0.75 ? 'extreme' : score >= 0.55 ? 'high' : score >= 0.30 ? 'moderate' : 'low';
export const ROLES = ['farmer', 'visitor', 'volunteer'];
