# route_service.py
import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class RouteService:
    GEOCODING_URL = "https://nominatim.openstreetmap.org/search"
    ROUTING_URL = "https://router.project-osrm.org/route/v1/driving"

    def __init__(self):
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        session.headers.update({'User-Agent': 'HOSApp/1.0 (contact@example.com)'})
        return session

    def geocode(self, location: str):
        params = {"q": location, "format": "json", "limit": 1}
        try:
            resp = self.session.get(self.GEOCODING_URL, params=params,headers={"User-Agent": "HOSApp"}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                raise ValueError(f"Location not found: {location}")
            return float(data[0]["lat"]), float(data[0]["lon"])
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Geocoding failed for '{location}': {str(e)}")

    def get_route_distance(self, lat1, lon1, lat2, lon2):
        coords = f"{lon1},{lat1};{lon2},{lat2}"
        url = f"{self.ROUTING_URL}/{coords}"
        try:
            resp = self.session.get(url, params={"overview": "false"}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data["code"] != "Ok":
                raise ValueError(f"Routing error: {data.get('message')}")
            return data["routes"][0]["distance"] / 1609.34  # meters to miles
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Routing failed: {str(e)}")

    def get_full_route_geometry(self, waypoints):
        """waypoints: list of (lat, lon) tuples"""
        coords = ";".join([f"{lon},{lat}" for lat, lon in waypoints])
        url = f"{self.ROUTING_URL}/{coords}?overview=full&geometries=polyline"
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if data["code"] != "Ok":
                return None
            return data["routes"][0]["geometry"]
        except Exception:
            return None