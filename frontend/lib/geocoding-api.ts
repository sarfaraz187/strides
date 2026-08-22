export async function reverseGeocode(lat: number, lon: number): Promise<string | null> {
  try {
    const response = await fetch(`https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${lat}&longitude=${lon}`);
    if (!response.ok) return null;
    const data = (await response.json()) as { city?: string; locality?: string };
    return data.city || data.locality || null;
  } catch {
    return null;
  }
}
