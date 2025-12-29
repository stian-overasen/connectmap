import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from garminconnect import Garmin
from tqdm import tqdm

load_dotenv()

app = FastAPI(title='Garmin Connect Map Viewer')

# Garmin session token from environment variable
GARMIN_SESSION = os.getenv('GARMIN_SESSION')
if not GARMIN_SESSION:
    raise ValueError('GARMIN_SESSION environment variable is required. Run setup_oauth.py to generate it.')

# Cache configuration
CACHE_DIR = Path('cache')
CACHE_DURATION_HOURS = 6  # Refresh cache every 6 hours
YEARS_TO_LOAD = 5  # Load last 5 years

# Ensure cache directory exists
CACHE_DIR.mkdir(exist_ok=True)


@app.get('/', response_class=HTMLResponse)
async def index():
    """Serve the main map page"""
    template_path = Path('templates/index.html')
    with open(template_path, 'r') as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)


def load_cache(year):
    """Load cached activities for a specific year if valid"""
    cache_file = CACHE_DIR / f'activities_cache_{year}.json'
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                if datetime.now() - cache_time < timedelta(hours=CACHE_DURATION_HOURS):
                    print(f'Using cached activities for {year}')
                    return cache_data['activities']
        except Exception as e:
            print(f'Error loading cache for {year}: {e}')
    return None


def save_cache(year, activities):
    """Save activities for a specific year to cache"""
    try:
        cache_file = CACHE_DIR / f'activities_cache_{year}.json'
        cache_data = {'timestamp': datetime.now().isoformat(), 'activities': activities}
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
        print(f'Cached {len(activities)} activities for {year}')
    except Exception as e:
        print(f'Error saving cache for {year}: {e}')


@app.get('/api/activities')
async def get_activities():
    """Fetch activities from the last 5 years"""
    try:
        current_year = datetime.now().year
        years = list(range(current_year - YEARS_TO_LOAD + 1, current_year + 1))

        all_activities = {}
        client = None

        for year in years:
            # Check cache first
            cached_activities = load_cache(year)
            if cached_activities is not None:
                all_activities[str(year)] = cached_activities
                continue

            # Login to Garmin Connect if not already logged in
            if client is None:
                client = Garmin()
                client.garth.loads(GARMIN_SESSION)

            # Get activities for this year
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31)

            print(f'\nFetching activities from {start_date.date()} to {end_date.date()}...')
            activities = client.get_activities_by_date(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
            print(f'Found {len(activities)} activities for {year}')

            # Process activities to extract relevant data including GPS tracks
            processed_activities = []
            print(f'Processing {year} activities and downloading GPS tracks...')
            for activity in tqdm(activities, desc=f'Loading {year}', unit='activity'):
                # Get detailed activity data including GPS coordinates
                activity_id = activity['activityId']
                try:
                    activity_details = client.get_activity(activity_id)

                    # Check if activity has GPS data
                    if activity_details and 'summaryDTO' in activity_details:
                        summary = activity_details['summaryDTO']

                        activity_name = activity.get('activityName', 'Unnamed Activity')
                        # Detect if activity is a race
                        is_race = any(
                            keyword in activity_name.lower()
                            for keyword in ['race', 'competition', 'løp', 'renn', 'konkurranse', 'cup']
                        )

                        processed_activity = {
                            'id': activity_id,
                            'name': activity_name,
                            'type': activity.get('activityType', {}).get('typeKey', 'unknown'),
                            'date': activity.get('startTimeLocal'),
                            'distance': activity.get('distance', 0) / 1000,  # Convert to km
                            'duration': activity.get('duration', 0),
                            'startLat': summary.get('startLatitude'),
                            'startLng': summary.get('startLongitude'),
                            'endLat': summary.get('endLatitude'),
                            'endLng': summary.get('endLongitude'),
                            'isRace': is_race,
                        }

                        # Get GPS track data
                        try:
                            gpx_data = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.GPX)
                            if gpx_data:
                                # Parse GPX to extract coordinates
                                import xml.etree.ElementTree as ET

                                root = ET.fromstring(gpx_data)
                                # GPX uses a namespace
                                ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
                                track_points = []

                                for trkpt in root.findall('.//gpx:trkpt', ns):
                                    lat = float(trkpt.get('lat'))
                                    lon = float(trkpt.get('lon'))
                                    track_points.append([lat, lon])

                                if track_points:
                                    processed_activity['track'] = track_points
                        except Exception as e:
                            print(f'\nError getting GPS track for activity {activity_id}: {e}')

                        # Only include activities with GPS coordinates
                        if processed_activity['startLat'] and processed_activity['startLng']:
                            processed_activities.append(processed_activity)
                except Exception as e:
                    print(f'\nError processing activity {activity_id}: {e}')
                    continue

            all_activities[str(year)] = processed_activities

            # Save to cache
            save_cache(year, processed_activities)

        if client:
            client.logout()

        return all_activities

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=5000)
