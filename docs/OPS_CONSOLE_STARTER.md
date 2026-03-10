# Operations Console Starter

`onTroFinanceStarter.py` starts the FastAPI backend and serves the built operations console from the same local web server.

## Local Run

```powershell
python onTroFinanceStarter.py
python onTroFinanceStarter.py --host 127.0.0.1 --port 8010 --no-browser
```

The starter:

- defaults to `ONTRO_STORAGE_BACKEND=inmemory` so it can boot without Neo4j
- uses `frontend/dist` when it exists
- serves the SPA and API from one process
- writes runtime data under the app home directory
- opens the browser automatically unless `--no-browser` is passed

## Build One-File EXE

```powershell
.\build_ops_console_exe.ps1
```

The build script:

- installs frontend dependencies
- builds `frontend/dist`
- installs Python dependencies into a temporary build virtual environment
- runs PyInstaller with `onTroFinanceStarter.spec`

Expected output:

- `dist/onTroFinanceStarter.exe`

## Packaged Runtime Notes

- Put `.env` next to the generated `.exe` if you need runtime overrides.
- If you want Neo4j instead of the standalone default, set `ONTRO_STORAGE_BACKEND=neo4j` in that `.env`.
- The packaged app reads bundled config files from the embedded resources.
- Runtime write paths such as `data/learning` are created next to the `.exe`.
