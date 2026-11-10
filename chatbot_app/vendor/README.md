# F1 Buddy deployment artifact

- Artifact: `f1buddy_ai-0.2.1-py3-none-any.whl` (pure Python).
- Source: sibling `f1buddy-ai` repository, branch `feature2`.
- Source commit: `c7262ecb52be73ef89bf0185b132191d3912b6c1`.
- Built: 2026-11-10, Python 3.12, Hatchling via pip.
- SHA-256: `8d7d50d6f7b6b0c845682d578e6a409f29e8af14cf9eb024130f900c5533aca1`.

From the Formula1 repository root:

```powershell
..\f1buddy-ai\.venv\Scripts\python.exe -B -m pip wheel --no-cache-dir --no-deps --no-build-isolation ../f1buddy-ai --wheel-dir chatbot_app/vendor
Get-FileHash chatbot_app/vendor/f1buddy_ai-0.2.1-py3-none-any.whl -Algorithm SHA256
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
