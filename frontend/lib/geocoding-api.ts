const GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search";

export type GeocodingResult = {
  name: string;
  latitude: number;
  longitude: number;
  admin1?: string;
  country?: string;
};

export async function searchCities(query: string): Promise<GeocodingResult[]> {
  if (query.trim().length < 2) return [];
  const response = await fetch(`${GEOCODING_URL}?name=${encodeURIComponent(query)}&count=5`);
  const data = await response.json();
  return data.results ?? [];
}
