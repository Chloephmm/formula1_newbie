/** Only configured Streamlit apps (or local development) can be embedded. */
export function getChatbotUrl(value: string | undefined, development = false): string | null {
  if (!value?.trim()) return null;
  try {
    const url = new URL(value.trim());
    if (url.username || url.password) return null;
    const hosted = url.protocol === "https:" && !url.port &&
      /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.streamlit\.app$/.test(url.hostname);
    const local = development && url.protocol === "http:" &&
      ["localhost", "127.0.0.1"].includes(url.hostname);
    if (!hosted && !local) return null;
    url.searchParams.set("embed", "true");
    return url.toString();
  } catch {
    return null;
  }
}
