import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from garminconnect import Garmin
from tqdm import tqdm

load_dotenv()

app = Flask(__name__)

# Garmin session token from environment variable
GARMIN_SESSION = os.getenv("GARMIN_SESSION")
if not GARMIN_SESSION:
    raise ValueError("GARMIN_SESSION environment variable is required. Run setup_oauth.py to generate it.")

# Cache configuration
CACHE_DIR = Path("cache")
YEARS_TO_LOAD = 10  # Load last 10 years
DB_PATH = CACHE_DIR / "activities.db"

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


@app.route("/")
def index():
    """Serve the main map page"""
    return render_template("index.html")


def load_all_cached_activities(years):
    """Load cached activities for all specified years in one query"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Load all activities for the specified years in one query
        placeholders = ",".join("?" * len(years))
        cursor.execute(
            f"""
            SELECT id, name, type, category, topLevelCategory, date,
                   distance, duration, startLat, startLng, endLat, endLng,
                   isRace, track, year
            FROM activities
            WHERE year IN ({placeholders})
        """,
            years,
        )

        # Group activities by year
        activities_by_year = {}
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
            if row[13]:  # track data
                activity["track"] = json.loads(row[13])

            year = row[14]
            if year not in activities_by_year:
                activities_by_year[year] = []
            activities_by_year[year].append(activity)

        conn.close()
        if activities_by_year:
            print(f"Loaded cached activities for {len(activities_by_year)} years (SQLite)")
        return activities_by_year

    except Exception as e:
        print(f"Error loading cached activities: {e}")
        return {}


def load_raw_cache():
    """Load raw Garmin API data from cache (current year + historical)"""
    current_cache = CACHE_DIR / "raw_cache_current.json"
    historical_cache = CACHE_DIR / "raw_cache_historical.json"

    raw_activities = []

    # Load historical cache
    if historical_cache.exists():
        try:
            with open(historical_cache) as f:
                historical_data = json.load(f)
                raw_activities.extend(historical_data["raw_activities"])
                print(f"Loaded {len(historical_data['raw_activities'])} historical activities from cache")
        except Exception as e:
            print(f"Error loading historical cache: {e}")

    # Load current year cache
    if current_cache.exists():
        try:
            with open(current_cache) as f:
                current_data = json.load(f)
                raw_activities.extend(current_data["raw_activities"])
                print(f"Loaded {len(current_data['raw_activities'])} current year activities from cache")
        except Exception as e:
            print(f"Error loading current year cache: {e}")

    return raw_activities if raw_activities else None


def save_raw_cache(raw_activities):
    """Save raw Garmin API data to cache (split by current year vs historical)"""
    try:
        current_year = datetime.now().year
        current_year_activities = []
        historical_activities = []

        for raw_activity in raw_activities:
            activity = raw_activity["activity"]
            activity_date = datetime.fromisoformat(activity.get("startTimeLocal", "").replace("Z", "+00:00"))
            if activity_date.year == current_year:
                current_year_activities.append(raw_activity)
            else:
                historical_activities.append(raw_activity)

        # Save current year cache
        if current_year_activities:
            current_cache = CACHE_DIR / "raw_cache_current.json"
            current_data = {"timestamp": datetime.now().isoformat(), "raw_activities": current_year_activities}
            with open(current_cache, "w") as f:
                json.dump(current_data, f, indent=2)
            print(f"Cached {len(current_year_activities)} current year activities")

        # Save historical cache
        if historical_activities:
            historical_cache = CACHE_DIR / "raw_cache_historical.json"
            historical_data = {"timestamp": datetime.now().isoformat(), "raw_activities": historical_activities}
            with open(historical_cache, "w") as f:
                json.dump(historical_data, f, indent=2)
            print(f"Cached {len(historical_activities)} historical activities")
    except Exception as e:
        print(f"Error saving raw cache: {e}")


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


@app.route("/api/refresh_current_year", methods=["POST"])
def refresh_current_year():
    """Refresh activities for the current year by clearing cache and refetching from API"""
    try:
        current_year = datetime.now().year

        # Delete current year raw cache
        current_cache = CACHE_DIR / "raw_cache_current.json"
        if current_cache.exists():
            current_cache.unlink()
            print("Deleted current year raw cache")

        # Delete current year from SQLite
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM activities WHERE year = ?", (current_year,))
        conn.commit()
        deleted_count = cursor.rowcount
        conn.close()
        print(f"Deleted {deleted_count} activities for {current_year} from database")

        # Fetch current year activities from Garmin API
        client = Garmin()
        client.garth.loads(GARMIN_SESSION)

        start_date = datetime(current_year, 1, 1)
        end_date = datetime.now()

        print(f"Fetching activities from {start_date.date()} to {end_date.date()}...")
        activities = client.get_activities_by_date(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        print(f"Found {len(activities)} activities for {current_year}")

        # Fetch raw data for each activity
        raw_activities = []
        print("Downloading raw data for current year activities...")
        for activity in tqdm(activities, desc="Downloading", unit="activity"):
            activity_id = activity["activityId"]
            try:
                activity_details = client.get_activity(activity_id)
                gpx_data = None
                try:
                    gpx_data = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.GPX)
                except Exception as e:
                    print(f"\nError downloading GPX for activity {activity_id}: {e}")

                raw_activities.append(
                    {
                        "activity": activity,
                        "details": activity_details,
                        "gpx": gpx_data.decode("utf-8") if gpx_data else None,
                    }
                )
            except Exception as e:
                print(f"\nError fetching data for activity {activity_id}: {e}")
                continue

        client.logout()

        # Save current year raw cache
        if raw_activities:
            current_cache_data = {"timestamp": datetime.now().isoformat(), "raw_activities": raw_activities}
            with open(current_cache, "w") as f:
                json.dump(current_cache_data, f, indent=2)
            print(f"Saved {len(raw_activities)} current year activities to cache")

        # Process and save to database
        processed_activities = []
        print("Processing current year activities...")
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
                            import xml.etree.ElementTree as ET

                            root = ET.fromstring(gpx_data)
                            ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
                            track_points = []

                            for trkpt in root.findall(".//gpx:trkpt", ns):
                                lat = float(trkpt.get("lat"))
                                lon = float(trkpt.get("lon"))
                                track_points.append([lat, lon])

                            if track_points:
                                processed_activity["track"] = track_points
                        except Exception as e:
                            print(f"\nError parsing GPX for activity {activity_id}: {e}")

                    if processed_activity["startLat"] and processed_activity["startLng"]:
                        processed_activities.append(processed_activity)
            except Exception as e:
                print(f"\nError processing activity: {e}")
                continue

        # Save to database
        if processed_activities:
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
                        current_year,
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
            print(f"Saved {len(processed_activities)} activities to database")

        return jsonify({str(current_year): processed_activities})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/activities")
def get_activities():
    """Fetch activities from the last 10 years"""
    try:
        current_year = datetime.now().year
        years = list(range(current_year - YEARS_TO_LOAD + 1, current_year + 1))

        # Try to load all cached activities in one query
        all_activities = load_all_cached_activities(years)

        # Check if database has any activities (if so, assume it's complete)
        if all_activities:
            # Database exists, return all years (including empty years)
            return jsonify({str(year): all_activities.get(year, []) for year in years})

        # Check raw cache
        raw_activities = load_raw_cache()
        if raw_activities is None:
            # Fetch from Garmin API
            client = Garmin()
            client.garth.loads(GARMIN_SESSION)

            # Get activities for all years at once
            start_date = datetime(years[0], 1, 1)
            end_date = datetime(years[-1], 12, 31)

            print(f"\nFetching activities from {start_date.date()} to {end_date.date()}...")
            activities = client.get_activities_by_date(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
            print(f"Found {len(activities)} activities")

            # Fetch raw data for each activity
            raw_activities = []
            print("Downloading raw data for activities...")
            for activity in tqdm(activities, desc="Downloading", unit="activity"):
                activity_id = activity["activityId"]
                try:
                    activity_details = client.get_activity(activity_id)
                    gpx_data = None
                    try:
                        gpx_data = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.GPX)
                    except Exception as e:
                        print(f"\nError downloading GPX for activity {activity_id}: {e}")

                    raw_activities.append(
                        {
                            "activity": activity,
                            "details": activity_details,
                            "gpx": gpx_data.decode("utf-8") if gpx_data else None,
                        }
                    )
                except Exception as e:
                    print(f"\nError fetching data for activity {activity_id}: {e}")
                    continue

            client.logout()

            # Save raw cache
            save_raw_cache(raw_activities)

        # Process raw activities
        activities_by_year = {}
        print("Processing activities...")
        for raw_activity in tqdm(raw_activities, desc="Processing", unit="activity"):
            try:
                activity = raw_activity["activity"]
                activity_details = raw_activity["details"]
                gpx_data = raw_activity["gpx"]
                activity_id = activity["activityId"]

                # Check if activity has GPS data
                if activity_details and "summaryDTO" in activity_details:
                    summary = activity_details["summaryDTO"]

                    activity_name = activity.get("activityName", "Unnamed Activity")
                    activity_type = activity.get("activityType", {}).get("typeKey", "unknown")

                    # Detect if activity is a race using eventType
                    event_type = activity.get("eventType", {})
                    is_race = event_type.get("typeKey") == "race" if event_type else False

                    # Categorize the activity
                    category, top_level_category = categorize_activity(activity_name, activity_type)

                    processed_activity = {
                        "id": activity_id,
                        "name": activity_name,
                        "type": activity_type,
                        "category": category,
                        "topLevelCategory": top_level_category,
                        "date": activity.get("startTimeLocal"),
                        "distance": activity.get("distance", 0) / 1000,  # Convert to km
                        "duration": activity.get("duration", 0),
                        "startLat": summary.get("startLatitude"),
                        "startLng": summary.get("startLongitude"),
                        "endLat": summary.get("endLatitude"),
                        "endLng": summary.get("endLongitude"),
                        "isRace": is_race,
                    }

                    # Parse GPX track data if available
                    if gpx_data:
                        try:
                            import xml.etree.ElementTree as ET

                            root = ET.fromstring(gpx_data)
                            # GPX uses a namespace
                            ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
                            track_points = []

                            for trkpt in root.findall(".//gpx:trkpt", ns):
                                lat = float(trkpt.get("lat"))
                                lon = float(trkpt.get("lon"))
                                track_points.append([lat, lon])

                            if track_points:
                                processed_activity["track"] = track_points
                        except Exception as e:
                            print(f"\nError parsing GPX for activity {activity_id}: {e}")

                    # Only include activities with GPS coordinates
                    if processed_activity["startLat"] and processed_activity["startLng"]:
                        # Determine year from date
                        activity_date = datetime.fromisoformat(processed_activity["date"].replace("Z", "+00:00"))
                        year = activity_date.year

                        if year not in activities_by_year:
                            activities_by_year[year] = []
                        activities_by_year[year].append(processed_activity)
            except Exception as e:
                print(f"\nError processing activity: {e}")
                continue

        # Save to cache
        save_all_activities(activities_by_year)

        return jsonify({str(year): activities_by_year.get(year, []) for year in years})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
