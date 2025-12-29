# Garmin Connect Map Viewer

A web application to visualize your Garmin Connect activities on an OpenStreetMap map with detailed
GPS tracks and category breakdowns.

## Features

- **Full GPS Track Visualization**: Displays complete activity routes on the map
- **2025 Activity Data**: Shows all activities from January 1 - December 31, 2025
- **Smart Categorization**:
  - Cross-country skiing (classic, skating, double poling)
  - Roller skiing (classic, skating, double poling)
  - Running (including trail and track running)
  - Automatic detection based on activity names
- **Color-Coded Display**:
  - Running: Red
  - Winter cross-country skiing: Blue
  - Roller skiing: Green
  - Other activities: Reduced opacity for focus
- **Category Statistics**: Grouped distance totals with subcategory breakdowns
- **Local Caching**: Activities cached for 6 hours to reduce API calls
- **Black & White Map**: Clean CartoDB Positron basemap for better activity visibility

## Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Garmin Connect account
- Active internet connection

## Installation

1. **Clone or navigate to the project directory:**

   ```bash
   cd /path/to/connectmap
   ```

2. **Install dependencies:**

   ```bash
   uv sync
   ```

   This will create a virtual environment and install all required packages.

## Configuration

### Setup Garmin Authentication

1. **Copy the environment template:**

   ```bash
   cp .env.example .env
   ```

2. **Generate OAuth session token:**

   ```bash
   uv run setup_oauth.py
   ```

   Follow the prompts to enter your Garmin Connect email and password. This is a one-time setup.

3. **Copy the generated token:**

   The script will output a `GARMIN_SESSION` token. Copy this value and add it to your `.env` file:

   ```
   GARMIN_SESSION=your_session_token_here
   ```

   **Note:** The session token is required. The application will not start without it.

## Running the Application

1. **Start the FastAPI server:**

   ```bash
   uv run app.py
   ```

   Or use uvicorn directly:

   ```bash
   uv run uvicorn app:app --host 0.0.0.0 --port 5000 --reload
   ```

   You'll see output showing the progress of loading activities:

   ```
   Fetching activities from 2025-01-01 to 2025-12-31...
   Found 150 activities
   Processing activities and downloading GPS tracks...
   Loading activities: 100%|████████| 150/150 [05:30<00:00, 2.2s/activity]
   ```

   **Note**: The first load may take several minutes as it downloads GPS data for all activities.

2. **Open your browser:**

   Navigate to [http://localhost:5000](http://localhost:5000)

3. **View your activities:**

   The map will display all your 2025 activities with GPS tracks color-coded by type.

## Cache Management

Activities are cached locally in `activities_cache.json` for 6 hours. To force a refresh:

```bash
rm activities_cache.json
```

Then restart the application.

## Development

### Scripts

The project includes helper scripts for common development tasks:

```bash
# Lint all code
./scripts/lint.sh

# Format all code (Python with ruff, Markdown with prettier)
./scripts/format.sh

# Run both lint and format
./scripts/check.sh
```

### Pre-commit Hooks

Pre-commit hooks are configured to automatically lint and format code before commits:

```bash
# Install pre-commit hooks (already done during setup)
uv run pre-commit install

# Run pre-commit on all files manually
uv run pre-commit run --all-files
```

Hooks include:

- Ruff linting and formatting (Python)
- Prettier formatting (Markdown)
- Trailing whitespace removal
- End-of-file fixes
- YAML/TOML validation
- Private key detection

### Code Formatting

The project uses:

- **Ruff** for Python linting and formatting
- **Prettier** for Markdown formatting

Both are configured to run automatically on save in VS Code and via pre-commit hooks.

Manual formatting:

```bash
uv run ruff check --fix .
uv run ruff format .
npx prettier --write "*.md"
```

## Technology Stack

- **Backend:** FastAPI (Python)
- **Frontend:** HTML, JavaScript, Leaflet.js
- **Maps:** OpenStreetMap (CartoDB Positron)
- **Data Source:** Garmin Connect API (OAuth)
- **Package Manager:** uv
