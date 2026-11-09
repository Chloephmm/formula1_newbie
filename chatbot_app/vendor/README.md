# F1 Buddy deployment artifact

- Artifact: `f1buddy_ai-0.2.0-py3-none-any.whl` (pure Python).
- Source: sibling `f1buddy-ai` repository, branch `feature2`.
- Source commit: `c351d19d77540e3ff962db5e6606fea7028e7821`.
- Built: 2026-11-09, Python 3.12, Hatchling via pip.
- SHA-256: `47ec81a93f7da109eb2dc6d7c570c10abea2a962c9d7f90d31d34a46ccbd417f`.

From the Formula1 repository root:

```powershell
..\f1buddy-ai\.venv\Scripts\python.exe -B -m pip wheel --no-cache-dir --no-deps --no-build-isolation ../f1buddy-ai --wheel-dir chatbot_app/vendor
Get-FileHash chatbot_app/vendor/f1buddy_ai-0.2.0-py3-none-any.whl -Algorithm SHA256
```

Both Streamlit requirements reference this exact wheel. It contains the chatbot
package and metadata, not model artifacts, datasets, credentials or dependency
wheels. Dependencies remain declared in the package metadata. No PyPI upload or
new public repository is needed.

Verified by importing directly from the wheel in isolated Python mode and running
the real chatbot entrypoint with Streamlit AppTest, including a saved-prediction
reply. A no-network pip dry-run also resolved the pinned requirements path.
For subsequent code changes, bump the package version, rerun tests, build a new
wheel, update both requirements and the exact `.gitignore` exception, then record
the new commit/hash here. Do not silently overwrite a published version.
