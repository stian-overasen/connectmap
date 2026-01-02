# Garmin Connect Map Viewer

A web application to visualize your Garmin Connect activities on an OpenStreetMap map with detailed
GPS tracks and category breakdowns.

## Features

- **Full GPS Track Visualization**: Displays complete activity routes on the map with Canvas
  rendering for optimal performance
- **Multi-Year Activity Data**: Shows all activities from the last 10 years with year-based
  filtering
- **Smart Categorization**:
  - Cross-country skiing (classic, skating, double poling)
  - Roller skiing (classic, skating, double poling)
  - Running (including trail and track running)
  - Automatic detection based on activity types and names
- **Race Detection**: Activities marked as races in Garmin Connect display trophy icons 🏆
- **Color-Coded Display**:
  - Running: Red variants (#FF4136 for running, #DC143C for trail, #FF6B6B for track)
  - Winter cross-country skiing: Blue (#0074D9)
  - Roller skiing: Green (#2ECC40)
  - Other activities: Grey gradients with reduced opacity
- **Category Statistics**: Grouped distance totals with subcategory breakdowns
- **Two-Tier Caching**:
  - Raw API data cached separately for faster reprocessing
  - Processed activities cached for 6 hours to reduce API calls
- **Year Filtering**: Toggle visibility of activities by year (all 10 years shown by default)
- **Black & White Map**: Clean CartoDB Positron basemap for better activity visibility

## Activity Categorization Logic

The application automatically categorizes activities based on Garmin activity types and naming
conventions:

### Cross-Country Skiing Categories

Activities are classified as cross-country skiing if the activity type includes:

- "cross_country_skiing"
- "cross" or "skiing"
- "multi_sport"

**Technique Detection** (applied to both winter and roller skiing):

1. **Double Poling**: Activity name contains "dp" or "stak"
2. **Skating**: Activity name or type contains "skat"
3. **Classic**: Activity name or type contains "classic", or used as default if no other technique
   detected

**Winter vs Roller Skiing**:

- **Roller Skiing**: Activity name contains "roller" → categorized as `roller_[technique]`
- **Winter XC Skiing**: All other XC activities → categorized as `xc_[technique]`

### Running Categories

- **Track Running**: Activity type is "track_running"
- **Trail Running**: Activity type is "trail_running"
- **Running**: All other running activity types

### Race Detection

Activities are marked as races (🏆) when `eventType.typeKey == "race"` in the Garmin API response.

### Other Activities

All other activity types (cycling, walking, etc.) are displayed with grey gradients and reduced
opacity.

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

1. **Start the Flask server:**

   ```bash
   uv run python app.py
   ```

   You'll see output showing the progress of loading activities:

   ```
   Fetching activities from 2016-01-01 to 2025-12-31...
   Found 150 activities for 2025
   Downloading raw data for 2025 activities...
   Downloading 2025: 100%|████████| 150/150 [03:30<00:00, 1.4s/activity]
   Processing 2025 activities...
   Processing 2025: 100%|████████| 150/150 [00:15<00:00, 9.7activity/s]
   Cached raw data for 150 activities in 2025
   Cached 148 activities for 2025
   ```

   **Note**: The first load may take several minutes per year as it downloads GPS data for all
   activities. Subsequent loads will use cached data.

2. **Open your browser:**

   Navigate to [http://localhost:5000](http://localhost:5000). You'll see a map showing all
   activities from the last 10 years with GPS tracks color-coded by type. Use the year checkboxes to
   filter which years are displayed.

## Cache Management

Activities are cached locally in the `cache/` directory with two cache types:

- **Raw cache** (`raw_cache_{year}.json`): Original API responses from Garmin
- **Processed cache** (`activities_cache_{year}.json`): Processed activity data for the map

Both caches expire after 6 hours. To force a refresh:

```bash
# Clear all caches (forces re-download from Garmin API)
rm -rf cache/

# Clear only processed caches (reprocesses from raw cache without API calls)
rm cache/activities_cache_*.json

# Clear single year cache
rm cache/activities_cache_2025.json cache/raw_cache_2025.json
```

Then restart the application.

## Development

### Scripts

The project includes helper scripts for common development tasks:

```bash
# Lint all code
./bin/lint.sh

# Format all code (Python with ruff, Markdown with prettier)
./bin/format.sh
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

- **Backend:** Flask (Python)
- **Frontend:** HTML, JavaScript, Leaflet.js
- **Maps:** OpenStreetMap (CartoDB Positron)
- **Data Source:** Garmin Connect API (OAuth)
- **Package Manager:** uv
