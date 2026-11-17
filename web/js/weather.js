// Live weather from Open-Meteo (https://open-meteo.com) — free, no API key.
// Shown next to the demo risk so people can see real current conditions.
// It does NOT change the risk colour, which comes from the (demo) model.

const ENDPOINT = 'https://api.open-meteo.com/v1/forecast';
const VARS = 'temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation';
const cache = new Map();
const TTL_MS = 10 * 60 * 1000; // 10 minutes

export async function getCurrentWeather(lat, lon, { signal } = {}) {
  const key = `${lat.toFixed(3)},${lon.toFixed(3)}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.data;

  const url = `${ENDPOINT}?latitude=${lat}&longitude=${lon}&current=${VARS}&timezone=auto`;
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`Open-Meteo responded ${res.status}`);
  const json = await res.json();
  if (!json.current) throw new Error('Open-Meteo returned no current data');

  const c = json.current;
  const data = {
    time: c.time, // local time of the observation slot, ISO without zone
    timezone: json.timezone_abbreviation || json.timezone || '',
    temperature: c.temperature_2m,
    humidity: c.relative_humidity_2m,
    wind: c.wind_speed_10m,
    precipitation: c.precipitation,
    units: json.current_units || {},
  };
  cache.set(key, { at: Date.now(), data });
  return data;
}
