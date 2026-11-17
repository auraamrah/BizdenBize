// Bite-sized education cards. Words live in locales/*.json → learn.tr / learn.id.
// Sources stay here (same in every language). `checked: false` = taken from the team's notes, not re-verified.
import { t } from './i18n.js';

export const SOURCES = {
  redpine: [{ label: 'Natural Hazards (2024): inventory of the 2021 forest fires in Türkiye', url: 'https://doi.org/10.1007/s11069-024-06622-0' }],
  blackpine: [
    { label: 'Natural Hazards (2024): 2021 fires inventory', url: 'https://doi.org/10.1007/s11069-024-06622-0' },
    { label: 'Keleş & Kavgacı (2025), Acta Botanica Croatica', url: 'https://doi.org/10.37427/botcro-2025-023' },
    { label: 'Cantürk et al. (2024), BioResources (OGM 2015 area)', url: 'https://bioresources.cnr.ncsu.edu/resources/possible-changes-of-pinus-nigra-distribution-regions-in-turkiye-with-the-impacts-of-global-climate-change/' },
  ],
  maquis: [{ label: 'General Directorate of Forestry figure, via Rufford Foundation', url: 'https://rufford.org/projects/irem-tüfekcioğlu/identifying-conservation-importance-of-maquis-habitats-and-developing-new-approaches-on-integrating-maquis-vegetation-to-forest-management-plans-in-turkey' }],
  twigs: [{ label: 'Crown fuel size classes of Turkish red pine (study shared by the team)', checked: false }],
  stands: [{ label: 'Stand structure study (shared by the team); Dimitrakopoulos & Papaioannou on eucalyptus flammability', checked: false }],
  rows: [{ label: 'Pausas et al. (2004); Moreira et al. (2011), cited in the team’s notes', checked: false }],
  season: [
    { label: '7th State of Environment Report of Türkiye', url: 'https://webdosya.csb.gov.tr/db/cis/edergi/7_State_Of_Environment_Report_Of_Turkiye/files/basic-html/page307.html' },
    { label: 'Daily Sabah: longer wildfire seasons', url: 'https://www.dailysabah.com/turkiye/experts-warn-turkiye-faces-longer-more-intense-wildfire-seasons/news/amp' },
  ],
  vulnerable: [{ label: 'Hürriyet Daily News: fire-season preparedness', url: 'https://hurriyetdailynews.com/amp/turkiye-steps-up-forest-fire-preparedness-as-risk-season-approaches-221534' }],
  peat: [{ label: 'Reuters via AsiaOne (Oct 2026): Pantau Gambut estimate', url: 'https://www.asiaone.com/asia/haze-indonesia-blames-peatland-degradation-raging-fires' }],
  idle: [{ label: 'Mongabay (2019): CIFOR analysis of 2019 burned area', url: 'https://news.mongabay.com/2019/12/indonesia-fires-forest-burning-land' }],
  riau: [{ label: 'Gaveau et al. (2014), Scientific Reports 4:6112 — CC BY 4.0', url: 'https://doi.org/10.1038/srep06112' }],
  tusam: [{ label: 'MDPI study on Pinus merkusii resin tapping (shared by the team)', checked: false }],
  east: [{ label: 'MapBiomas Fire Indonesia, Jan–Jun 2026 factsheet (Auriga)', url: 'https://auriga.or.id/resource/reference/factsheet-mapbiomas-fire-monthly.pdf' }],
  gelam: [{ label: 'CIFOR-ICRAF (shared by the team)', checked: false }],
  alang: [{ label: 'J-STAGE study on Imperata cylindrica (shared by the team)', checked: false }],
};

function twigsVisual() {
  const labels = t('learn.twigLabels');
  const widths = [2, 4, 7, 12];
  return `<div class="twigs" aria-hidden="true">${labels.map((l, i) => `<div class="twig"><span>${l}</span><i style="height:${widths[i]}px;width:${100 - i * 8}%"></i></div>`).join('')}</div>`;
}
function riauVisual() {
  // Gaveau et al. 2014, Fig. 3 — share of the 163,336 ha burned in June 2013, by land cover seen by LANDSAT
  const parts = [['nonforest', 82, '#b45309'], ['forest', 7, '#15803d'], ['acacia', 3, '#65a30d'], ['cloud', 8, '#94a3b8']];
  const lg = t('learn.riauLegend');
  return `<div><div class="stackbar" role="img" aria-label="${parts.map(([k, v]) => `${lg[k]} ${v}%`).join(', ')}">${parts.map(([, v, c]) => `<span style="width:${v}%;background:${c}">${v >= 7 ? v + '%' : ''}</span>`).join('')}</div>
    <div class="stack-legend">${parts.map(([k, v, c]) => `<span><i style="background:${c}"></i>${lg[k]} ${v}%</span>`).join('')}</div></div>`;
}

export function learnCards(country) {
  const cards = t(`learn.${country}`);
  return cards.map(c => {
    const src = SOURCES[c.id] || [];
    const visual = c.visual === 'twigs' ? twigsVisual() : c.visual === 'riau' ? riauVisual() : '';
    return `<article class="card learn">
      <span class="learn__icon" aria-hidden="true">${c.icon}</span>
      <h3>${c.title}</h3>
      <p class="learn__simple">${c.simple}</p>
      ${visual}
      ${c.num ? `<div class="learn__num"><b>${c.num}</b><span>${c.numLabel}</span></div>` : ''}
      <details><summary>${t('learn.more')}</summary><p>${c.more}</p>
        <p class="learn__src">${t('learn.source')}: ${src.map(s => s.url ? `<a href="${s.url}" target="_blank" rel="noopener">${s.label}</a>` : s.label).join(' · ')}</p></details>
    </article>`;
  }).join('');
}
