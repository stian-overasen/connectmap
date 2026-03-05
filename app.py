import json
import os
import sqlite3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from garminconnect import Garmin
from tqdm import tqdm

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP: Any = None

load_dotenv()

app = Flask(__name__)

# Garmin session token from environment variable
GARMIN_SESSION = os.getenv("GARMIN_SESSION")
if not GARMIN_SESSION:
    raise ValueError("GARMIN_SESSION environment variable is required. Run setup_oauth.py to generate it.")

# Cache configuration
CACHE_DIR = Path(__file__).parent / "cache"
YEARS_TO_LOAD = 10  # Load last 10 years
DB_PATH = CACHE_DIR / "activities.db"
COORDS_SUBSAMPLE_EVERY_N = 10  # Keep every Nth point to reduce cache and API payload size

# Ensure cache directory exists
CACHE_DIR.mkdir(exist_ok=True)


def init_db():
    """Initialize SQLite database for caching activities"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY,
            year INTEGER NOT NULL,
            name TEXT,
            type TEXT,
            category TEXT,
            topLevelCategory TEXT,
            date TEXT,
            distance REAL,
            duration INTEGER,
            startLat REAL,
            startLng REAL,
            endLat REAL,
            endLng REAL,
            isRace INTEGER,
            track TEXT,
            cache_timestamp TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_year ON activities(year)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_timestamp ON activities(cache_timestamp)")
    conn.commit()
    conn.close()


# Initialize database on startup
init_db()

# Category definitions
XC_CATEGORIES = [
    "xc_classic",
    "xc_skating",
    "xc_double_poling",
    "roller_classic",
    "roller_skating",
    "roller_double_poling",
]
RUNNING_CATEGORIES = ["running", "track_running", "trail_running"]
WALKING_CATEGORIES = ["walking", "hiking"]


def categorize_activity(activity_name, activity_type):
    """Categorize an activity based on name and type"""
    activity_name_lower = (activity_name or "").lower()
    activity_type_lower = (activity_type or "").lower()

    # Check if it's a cross-country skiing activity
    is_cross_country = (
        "cross" in activity_type_lower
        or "skiing" in activity_type_lower
        or activity_type_lower == "cross_country_skiing"
        or activity_type_lower == "multi_sport"
    )

    if is_cross_country:
        # Check if it's roller skiing
        is_roller = "roller" in activity_name_lower

        # Determine the technique
        technique = "classic"  # default

        if "dp" in activity_name_lower or "stak" in activity_name_lower:
            technique = "double_poling"
        elif "skat" in activity_name_lower or "skat" in activity_type_lower:
            technique = "skating"
        elif "classic" in activity_name_lower or "classic" in activity_type_lower:
            technique = "classic"

        # Return the appropriate category
        if is_roller:
            category = f"roller_{technique}"
        else:
            category = f"xc_{technique}"

        return category, "Cross Country"

    # Merge hiking into walking
    type_normalized = activity_type_lower.replace(" ", "_")
    if type_normalized == "hiking":
        return "walking", "Walking"

    # Determine top-level category
    if type_normalized in RUNNING_CATEGORIES or "running" in type_normalized:
        top_level = "Running"
    elif type_normalized in WALKING_CATEGORIES or "walking" in type_normalized:
        top_level = "Walking"
    else:
        top_level = "Other"

    return type_normalized, top_level


def subsample_coords(coords, every_n=COORDS_SUBSAMPLE_EVERY_N):
    """Subsample coordinates by keeping every nth point while preserving the final point."""
    if every_n <= 1 or len(coords) <= 2:
        return coords

    subsampled = coords[::every_n]
    if subsampled[-1] != coords[-1]:
        subsampled.append(coords[-1])
    return subsampled


@app.route("/")
def index():
    """Serve the main map page"""
    return render_template("index.html")


def get_garmin_client():
    """Create and authenticate Garmin Connect client using stored session."""
    if GARMIN_SESSION is None:
        raise ValueError("GARMIN_SESSION environment variable is required. Run setup_oauth.py to generate it.")

    client = Garmin()
    client.garth.loads(GARMIN_SESSION)
    return client


def parse_required_year(year_value, field_name):
    """Parse and validate a required year value."""
    if year_value in (None, ""):
        raise ValueError(f"Missing required {field_name}. Expected a year like 2025.")

    try:
        parsed_year = int(year_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}: {year_value}. Expected a year like 2025.") from exc

    max_year = datetime.now().year + 1
    if parsed_year < 1900 or parsed_year > max_year:
        raise ValueError(f"Invalid {field_name}: {year_value}. Expected a value between 1900 and {max_year}.")

    return parsed_year


def parse_bool(value, field_name="value"):
    """Parse bool-like values for MCP tool inputs."""
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n", ""}:
            return False

    raise ValueError(f"Invalid {field_name}: {value}. Expected true/false.")


def load_cached_activities_for_year(year):
    """Load cached activities for a single year from SQLite."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, type, category, topLevelCategory, date,
                   distance, duration, startLat, startLng, endLat, endLng,
                   isRace, track
            FROM activities
            WHERE year = ?
        """,
            (year,),
        )
        activities = []
        for row in cursor.fetchall():
            activity = {
                "id": row[0],
                "name": row[1],
                "type": row[2],
                "category": row[3],
                "topLevelCategory": row[4],
                "date": row[5],
                "distance": row[6],
                "duration": row[7],
                "startLat": row[8],
                "startLng": row[9],
                "endLat": row[10],
                "endLng": row[11],
                "isRace": bool(row[12]),
            }
            if row[13]:
                activity["track"] = json.loads(row[13])
            activities.append(activity)
        conn.close()
        return activities
    except Exception as e:
        print(f"Error loading cached activities for {year}: {e}")
        return []


def load_raw_cache(year):
    """Load raw Garmin API data for a specific year from cache."""
    cache_file = CACHE_DIR / f"raw_cache_{year}.json"
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                data = json.load(f)
                print(f"Loaded {len(data['raw_activities'])} activities from raw cache for {year}")
                return data["raw_activities"]
        except Exception as e:
            print(f"Error loading raw cache for {year}: {e}")
    return None


def save_raw_cache(year, raw_activities):
    """Save raw Garmin API data to cache for a specific year."""
    try:
        cache_file = CACHE_DIR / f"raw_cache_{year}.json"
        data = {"timestamp": datetime.now().isoformat(), "raw_activities": raw_activities}
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Cached {len(raw_activities)} activities for {year} (raw cache)")
    except Exception as e:
        print(f"Error saving raw cache for {year}: {e}")


def save_all_activities(activities_by_year):
    """Save all activities to cache"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Clear all existing data
        cursor.execute("DELETE FROM activities")

        # Insert all activities
        cache_timestamp = datetime.now().isoformat()
        for year, activities in activities_by_year.items():
            for activity in activities:
                track_json = json.dumps(activity.get("track")) if activity.get("track") else None
                cursor.execute(
                    """
                    INSERT INTO activities (
                        id, year, name, type, category, topLevelCategory, date,
                        distance, duration, startLat, startLng, endLat, endLng,
                        isRace, track, cache_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        activity["id"],
                        year,
                        activity["name"],
                        activity["type"],
                        activity["category"],
                        activity["topLevelCategory"],
                        activity["date"],
                        activity["distance"],
                        activity["duration"],
                        activity["startLat"],
                        activity["startLng"],
                        activity["endLat"],
                        activity["endLng"],
                        int(activity["isRace"]),
                        track_json,
                        cache_timestamp,
                    ),
                )

        conn.commit()
        conn.close()
        total = sum(len(acts) for acts in activities_by_year.values())
        print(f"Cached {total} activities across {len(activities_by_year)} years (SQLite)")
    except Exception as e:
        print(f"Error saving cache: {e}")


def clear_cache_for_year(year):
    """Clear raw and processed cache for a specific year."""
    cache_file = CACHE_DIR / f"raw_cache_{year}.json"
    if cache_file.exists():
        cache_file.unlink()
        print(f"Deleted raw cache for year {year}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM activities WHERE year = ?", (year,))
    conn.commit()
    conn.close()
    print(f"Deleted activities for {year} from database")


def fetch_raw_activities_from_garmin(year):
    """Fetch raw activity payloads (activity, details, gpx) from Garmin for one year."""
    client = get_garmin_client()
    try:
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)
        print(f"Fetching activities from {start_date.date()} to {end_date.date()}...")
        activities_list = client.get_activities_by_date(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        print(f"Found {len(activities_list)} activities for {year}")

        raw_activities = []
        print(f"Downloading raw data for year {year} activities...")
        for activity in tqdm(activities_list, desc="Downloading", unit="activity"):
            activity_id = activity["activityId"]
            try:
                activity_details = client.get_activity(activity_id)
                gpx_data = None
                try:
                    gpx_data = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.GPX)
                except Exception as e:
                    print(f"\nError downloading GPX for activity {activity_id}: {e}")

                raw_activities.append({"activity": activity, "details": activity_details, "gpx": gpx_data.decode("utf-8") if gpx_data else None})
            except Exception as e:
                print(f"\nError fetching data for activity {activity_id}: {e}")
                continue

        return raw_activities
    finally:
        try:
            client.logout()
        except Exception as e:
            print(f"Error logging out Garmin client: {e}")


def process_raw_activities_for_year(raw_activities, year):
    """Transform raw Garmin payloads into map-ready activities."""
    processed_activities = []
    print(f"Processing year {year} activities...")

    for raw_activity in tqdm(raw_activities, desc="Processing", unit="activity"):
        try:
            activity = raw_activity["activity"]
            activity_details = raw_activity["details"]
            gpx_data = raw_activity["gpx"]
            activity_id = activity["activityId"]

            if activity_details and "summaryDTO" in activity_details:
                summary = activity_details["summaryDTO"]
                activity_name = activity.get("activityName", "Unnamed Activity")
                activity_type = activity.get("activityType", {}).get("typeKey", "unknown")
                event_type = activity.get("eventType", {})
                is_race = event_type.get("typeKey") == "race" if event_type else False
                category, top_level_category = categorize_activity(activity_name, activity_type)
                processed_activity = {
                    "id": activity_id,
                    "name": activity_name,
                    "type": activity_type,
                    "category": category,
                    "topLevelCategory": top_level_category,
                    "date": activity.get("startTimeLocal"),
                    "distance": activity.get("distance", 0) / 1000,
                    "duration": activity.get("duration", 0),
                    "startLat": summary.get("startLatitude"),
                    "startLng": summary.get("startLongitude"),
                    "endLat": summary.get("endLatitude"),
                    "endLng": summary.get("endLongitude"),
                    "isRace": is_race,
                }

                if gpx_data:
                    try:
                        root = ET.fromstring(gpx_data)
                        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
                        track_points = []
                        for trkpt in root.findall(".//gpx:trkpt", ns):
                            lat_str = trkpt.get("lat")
                            lon_str = trkpt.get("lon")
                            if lat_str is None or lon_str is None:
                                continue

                            lat = float(lat_str)
                            lon = float(lon_str)
                            track_points.append([lat, lon])
                        if track_points:
                            processed_activity["track"] = subsample_coords(track_points)
                    except Exception as e:
                        print(f"\nError parsing GPX for activity {activity_id}: {e}")

                if processed_activity["startLat"] and processed_activity["startLng"]:
                    processed_activities.append(processed_activity)
        except Exception as e:
            print(f"\nError processing activity: {e}")
            continue

    return processed_activities


def save_processed_activities_for_year(year, processed_activities):
    """Persist processed activities for a year in SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cache_timestamp = datetime.now().isoformat()

    for activity in processed_activities:
        track_json = json.dumps(activity.get("track")) if activity.get("track") else None
        cursor.execute(
            """
            INSERT INTO activities (
                id, year, name, type, category, topLevelCategory, date,
                distance, duration, startLat, startLng, endLat, endLng,
                isRace, track, cache_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                activity["id"],
                year,
                activity["name"],
                activity["type"],
                activity["category"],
                activity["topLevelCategory"],
                activity["date"],
                activity["distance"],
                activity["duration"],
                activity["startLat"],
                activity["startLng"],
                activity["endLat"],
                activity["endLng"],
                int(activity["isRace"]),
                track_json,
                cache_timestamp,
            ),
        )

    conn.commit()
    conn.close()
    print(f"Saved {len(processed_activities)} activities to database for year {year}")


def fetch_activities_for_year(year, clear_cache=False):
    """Fetch activities for a specific year, optionally clearing cache first."""
    if clear_cache:
        clear_cache_for_year(year)

    activities = load_cached_activities_for_year(year)
    if activities and not clear_cache:
        return activities

    raw_activities = load_raw_cache(year)
    if raw_activities is None or clear_cache:
        raw_activities = fetch_raw_activities_from_garmin(year)
        if raw_activities:
            save_raw_cache(year, raw_activities)

    processed_activities = process_raw_activities_for_year(raw_activities, year)
    if processed_activities:
        save_processed_activities_for_year(year, processed_activities)

    return processed_activities


@app.route("/api/activities/<int:year>", methods=["GET"])
def get_activities_for_year(year):
    """Fetch activities for a specific year, optionally clearing cache."""
    try:
        clear_cache = request.args.get("clear_cache", "false").lower() == "true"
        activities = fetch_activities_for_year(year, clear_cache=clear_cache)
        return jsonify({str(year): activities})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def create_mcp_server():
    """Create an MCP server exposing activity endpoint tools."""
    if FastMCP is None:
        raise RuntimeError("MCP support requires the 'mcp' package. Run 'uv sync' to install dependencies.")

    mcp = FastMCP("connectmap")

    @mcp.tool(name="fetch_activities_for_year")
    def mcp_fetch_activities_for_year(year, clear_cache=False):
        """Fetch Garmin activities for one calendar year.

        Args:
            year: Calendar year (for example: 2025).
            clear_cache: Optional true/false value to force cache refresh.
        """
        parsed_year = parse_required_year(year, "year")
        parsed_clear_cache = parse_bool(clear_cache, "clear_cache")
        activities = fetch_activities_for_year(parsed_year, clear_cache=parsed_clear_cache)
        return {str(parsed_year): activities}

    @mcp.tool(name="fetch_activities_for_year_range")
    def mcp_fetch_activities_for_year_range(start_year, end_year, clear_cache=False):
        """Fetch Garmin activities for an inclusive year range.

        Args:
            start_year: Start year (inclusive).
            end_year: End year (inclusive).
            clear_cache: Optional true/false value to force cache refresh.
        """
        parsed_start_year = parse_required_year(start_year, "start_year")
        parsed_end_year = parse_required_year(end_year, "end_year")
        if parsed_start_year > parsed_end_year:
            raise ValueError("start_year must be before or equal to end_year.")

        parsed_clear_cache = parse_bool(clear_cache, "clear_cache")
        activities_by_year = {}
        for year in range(parsed_start_year, parsed_end_year + 1):
            activities_by_year[str(year)] = fetch_activities_for_year(year, clear_cache=parsed_clear_cache)

        return activities_by_year

    return mcp


def run_flask_server():
    """Run Flask map server."""
    print("Garmin Connect Map Viewer")
    print("=" * 50)
    print("Starting Flask server on http://127.0.0.1:5000")
    print("API endpoints:")
    print("  /api/activities/<year> - Activities for a specific year (JSON)")
    print("Parameters:")
    print("  clear_cache=true (optional; forces cache refresh)")
    print()
    app.run()


def run_mcp_server():
    """Run MCP server exposing activities tools over stdio."""
    mcp_server = create_mcp_server()
    print("Garmin Connect Map Viewer MCP server")
    print("=" * 50)
    print("Starting MCP server over stdio")
    print("Tools:")
    print("  fetch_activities_for_year(year, clear_cache=false)")
    print("  fetch_activities_for_year_range(start_year, end_year, clear_cache=false)")
    mcp_server.run()


if __name__ == "__main__":
    if "--mcp" in sys.argv:
        run_mcp_server()
    else:
        run_flask_server()
