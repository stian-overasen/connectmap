# Copilot Instructions - Garmin Connect Map Viewer

## Project Overview

A Flask web application that visualizes Garmin Connect activities on OpenStreetMap with GPS tracks.
Single-file backend ([app.py](../app.py)) serves a Leaflet.js frontend
([templates/index.html](../templates/index.html)) displaying activities from the last 10 years with
smart categorization.

## Architecture & Data Flow

### Authentication Flow (Critical)

1. User runs `uv run setup_oauth.py` once to generate `GARMIN_SESSION` token via email/password
2. Token stored in `.env` (gitignored), loaded via `python-dotenv` in [app.py](../app.py)
3. `Garmin().garth.loads(GARMIN_SESSION)` restores session without repeated logins
4. **Never** commit credentials - only use `.env.example` for templates

### Activity Data Pipeline

```
Garmin API → Per-Year Cache (6h TTL) → Flask /api/activities → Leaflet Map
```

- [app.py](../app.py#L65-L160): Fetches activities from last 5 years, downloads GPX data, parses XML
  for coordinates
- Each year cached separately in `cache/activities_cache_{year}.json` for faster subsequent loads
- GPX track parsing uses `xml.etree.ElementTree` with namespace
  `{'gpx': 'http://www.topografix.com/GPX/1/1'}`
- Cache files contain personal data - always gitignored (entire `cache/` directory)
- Initial load per year takes ~2-5 minutes - progress shown with `tqdm` for each year
- API returns object with years as keys: `{"2021": [...], "2022": [...], ...}`

### Frontend Categorization Logic

[templates/index.html](../templates/index.html#L178-L227) categorizes activities via naming
conventions:

- **Running**: `activity.type` contains "running"
- **Winter XC skiing**: Type contains "cross"/"skiing" + NO "roller" in name
- **Roller skiing**: Same but WITH "roller" in name
- **Technique detection**: "dp"/"stak" → double poling, "skat" → skating, else classic
- **Race detection**: [app.py](../app.py) checks activity name for keywords ("race", "løp", "renn",
  "konkurranse", "cup")

Color scheme: Running=Red (#FF4136), XC=Blue (#0074D9), Roller=Green (#2ECC40) Race markers: Trophy
emoji (🏆) displayed at start position with higher z-index

### Year Filtering System

Frontend maintains global state for filtering activities by year:

- `allActivitiesByYear`: Object storing all activities keyed by year
- `selectedYears`: Set tracking which year checkboxes are checked
- `mapLayers`: Array of Leaflet layers for efficient clearing/redrawing
- Year checkboxes auto-generated from API response, all checked by default
- `updateMap()` redraws map when filters change, `updateStats()` recalculates totals

````

Default view: [http://localhost:5000](http://localhost:5000) - Map auto-centers on all activities

### Code Quality Pipeline
All enforced via [pre-commit](../.pre-commit-config.yaml):
```bash
./bin/check.sh     # Lint + format (recommended before commits)
./bin/lint.sh      # Python: ruff check
./bin/format.sh    # Python: ruff format + Markdown: prettier
````

**Ruff configuration** ([pyproject.toml](../pyproject.toml#L33-L56)):

- 120 char line length, single quotes, 4-space indent
- Select: E, F, W, I (pycodestyle + Pyflakes + import sorting)
- Auto-fix enabled for all rules

**IMPORTANT**: Always run `./bin/check.sh` after making code changes to ensure formatting and
linting compliance.

### Testing Changes

1. Clear cache to test API changes: `rm -rf cache/` (removes all year caches)
2. Clear single year: `rm cache/activities_cache_{year}.json`
3. Debug mode automatically reloads Flask on file changes (`debug=True`)
4. Check browser console for frontend JavaScript errors

### Python Style

- Single quotes everywhere (`'string'` not `"string"`)
- Type hints minimal - Flask routes return plain dicts/JSON
- Exception handling: Broad `except Exception` with user-friendly `jsonify({'error': str(e)}), 500`
- Progress indicators: Use `tqdm` for long operations (see activity processing loop)

### File Organization

- Single backend file [app.py](../app.py) - no modules/packages structure
- Templates in [templates/](../templates/) - plain HTML with inline CSS/JS
- No static file serving - CDN links for Leaflet.js
- Scripts in [bin/](../bin/) - bash only, use `uv run` for Python commands

### Security Patterns

**Always enforce**:

- Credentials ONLY in `.env` (check [.gitignore](../.gitignore))
- Personal data files: `cache/` directory (all year caches), `oauth_tokens.txt` must be gitignored
- Pre-commit hook detects hardcoded keys (see [PRE_COMMIT_CHECKLIST.md](../PRE_COMMIT_CHECKLIST.md))
- OAuth tokens expire - users re-run `setup_oauth.py` on `401` errors

## Common Tasks

### Adding New Activity Categories

1. Update color map in [index.html](../templates/index.html#L116-L129)
2. Modify `categorizeActivity()` logic (lines 178-227)
3. Add to `focusCategories` array for full opacity (line 176)

### Changing Date Range

Change `YEARS_TO_LOAD = 5` in [app.py](../app.py#L24) - affects how many years back to load Current
implementation loads last 5 years dynamically based on current date

### Modifying Cache Duration

Change `CACHE_DURATION_HOURS = 6` in [app.py](../app.py#L23)

### Adding/Removing Years from Filter

Years are auto-generated from API response - no manual configuration needed Frontend creates
checkboxes for all years returned by backend

## Dependencies & Package Management

Uses `uv` (not pip/poetry):

- [pyproject.toml](../pyproject.toml) defines `dependencies` + `[dependency-groups.dev]`
- Install: `uv sync` (creates `.venv/`)
- Add package: `uv add <package>` (auto-updates pyproject.toml)
- Dev packages: `uv add --dev <package>`

**Key dependencies**:

- `garminconnect` (unofficial API client - may break on Garmin changes)
- `flask` (lightweight WSGI web framework)
- `python-dotenv` (environment variables)
- `tqdm` (progress bars)

## Known Quirks

1. **Garmin API rate limits**: Cache exists to prevent excessive calls - respect 6h TTL per year
2. **GPX namespace required**: XML parsing fails without
   `ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}`
3. **Activity type inconsistency**: Garmin uses `activityType.typeKey` + `activityName` - both
   needed for categorization
4. **Multi-sport handling**: Grouped activities may have misleading types - rely on name parsing
5. **No database**: All state in per-year JSON caches - concurrent requests share same files (not
   production-ready)
6. **Year boundaries**: Activities loaded by calendar year (Jan 1 - Dec 31), not rolling 12-month
   periods
