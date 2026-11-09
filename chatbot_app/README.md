# F1 Buddy on both websites

The prediction dashboard keeps its native popup and displayed prediction context.
The Next.js website has one floating **Ask F1 Buddy** launcher on every route. It
loads this separate Streamlit app only when opened, using the same Python package.
It does not embed or execute the ML dashboard.

## Local preview

Run from the **Formula1 repository root**, using Python 3.12:

```powershell
python -m pip install -r chatbot_app/requirements.txt
python -m streamlit run chatbot_app/app.py --server.port 8519
```

In another terminal, from `Formula1/web`:

```powershell
npm ci
$env:NEXT_PUBLIC_F1BUDDY_URL = 'http://127.0.0.1:8519'
npm run dev -- --port 3020
```

Open `http://localhost:3020`. Loopback HTTP is allowed only in development;
production requires an HTTPS, single-subdomain `*.streamlit.app` URL. The helper
adds `embed=true`. `web/.env.example` documents the setting. It is a public URL,
not a secret. An absent/invalid setting shows setup guidance rather than a broken
iframe. Restart the development server after changing the setting.

For the native prediction dashboard, install `streamlit_app/requirements.txt`
from the repository root and run `streamlit_app/app.py` in its normal environment.
The full dashboard may execute its existing ML behavior; it is not needed to
test this chatbot-only app.

## Deployment checklist (not performed by this implementation)

1. Review and publish the scoped `feature2` changes through your normal release
   process. Keep the wheel, both requirements, and new app entrypoint together.
2. In Streamlit Community Cloud, create a **separate** app from your existing
   `formula1_newbie` repository and intended deployment branch. Set the main file
   to `chatbot_app/app.py` and Python to 3.12. Its adjacent requirements install
   the checked-in wheel, with paths resolved from the repository root.
3. An embedded Community Cloud app must be public. Review the read-only outputs
   it can expose before making it public. Do not put secrets in these outputs.
   Copy the actual URL assigned by Streamlit; no production URL is invented here.
4. In the existing Vercel project's environment settings, set
   `NEXT_PUBLIC_F1BUDDY_URL` to that URL for the desired Preview/Production
   environments. The Next.js project root remains `web`. Rebuild/redeploy:
   `NEXT_PUBLIC_*` values are embedded at build time, not changed at runtime.
5. Redeploy the existing prediction app with the updated
   `streamlit_app/requirements.txt`, which installs the identical wheel. Its
   existing `streamlit_app/app.py` entrypoint and ML behavior are unchanged.
6. Verify both hosted sites: launcher, saved prediction date/mode, historical
   question, close/reopen, and direct-open fallback. Do not mark rollout complete
   solely because the local preview or an iframe load event succeeds.

Official embedding reference:
[Streamlit Community Cloud embedding](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app/embed-your-app).

## Data and limitations

- The native popup copies the dashboard's displayed prediction. The standalone
  panel reads JSON from **its own deployed checkout** at `web/public/data`.
  Deployments must receive updated outputs through the existing release process;
  this is not a live connection to another dashboard or Vercel deployment.
- Saved forecasts explicitly show their race/date/mode and may be older than
  today. Missing predictions are never recomputed. Historical detailed stages
  exist only while the original outputs retain them; the chatbot creates no archive.
- Existing Jolpica GET fallback remains available for factual data. Caches and
  conservative throttles are per Python process, not shared between the two apps.
  Provider limits may also count other applications behind the same IP.
- No ML, strategy, dataset, export, refresh workflow, database, AI model, RAG,
  WhatsApp, or scheduler is added or changed by this integration.
- Chat histories are separate between apps, session-only and capped at 20 messages.
  Closing/reopening the website panel preserves its iframe for the current page
  session. Browser refresh or hosting restarts can lose that session.
- Close and the launcher toggle remain available outside the iframe. Escape
  closes the panel while focus is on the parent website. Browsers do not pass
  keyboard events out of a cross-origin iframe; use Close or tab out when typing
  inside Streamlit. This is a non-modal panel and does not trap keyboard focus.
- Small screens scroll inside the embedded app. A direct-open link remains
  available for sleeping apps, third-party embedding restrictions, or more space.
  If waking the app does not recover the embed, refresh the website (resets chat).

## Verification

```powershell
# From Formula1/web:
npm run test:chatbot
npx eslint components/F1Buddy.tsx lib/chatbot.ts tests/chatbot.test.ts app/layout.tsx
npx tsc --noEmit
npm run build

# From the sibling f1buddy-ai repository:
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider
```

Package provenance and artifact hash are recorded in [vendor/README.md](vendor/README.md).
