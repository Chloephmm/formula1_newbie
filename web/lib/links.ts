// External links. The "Predict" tab points to the separate Streamlit app.
// Set NEXT_PUBLIC_STREAMLIT_URL in .env / Vercel; falls back to a placeholder.
export const STREAMLIT_URL =
  process.env.NEXT_PUBLIC_STREAMLIT_URL ?? "https://f1forecast.streamlit.app/";
