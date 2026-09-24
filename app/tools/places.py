import requests
from app import config
# =================================================
#                       Geocode
# =================================================
HEADERS = {"User-Agent": config.USER_AGENT}

def geocode(address: str) -> dict:
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1, "countrycodes": "vn"}

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)        
        resp.raise_for_status()
        results = resp.json()

        if not results:
            return {"found": False, "address": address}

        r = results[0]
        return {
            "found": True,
            "address": address,
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
            "display_name": r["display_name"],
        }
    except Exception as e:
        print(f"Loi ket noi Nominatim: {e}")
        return {"found": False, "address": address}


# =================================================
#                     Search Places
# =================================================
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
MAX_SEARCH_LIMIT = 10
CATEGORY_TAGS = {
    "attraction": '["tourism"~"museum|attraction|viewpoint|artwork|gallery|zoo"]',
    "restaurant": '["amenity"~"restaurant|cafe|fast_food"]'
}


def query_overpass(query, timeout=15):
    headers = {
        "User-Agent": "GuidePassAgent/1.0",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }

    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("elements", [])
    except requests.exceptions.RequestException as e:
        print(f"Lỗi kết nối Overpass API: {e}")
        raise e

def search_places(category, near_lat, near_lon, vegetarian=False, radius_m=5000, limit=5):
    if category not in CATEGORY_TAGS:
        return {"error": f"invalid category {category!r}; must be one of {sorted(CATEGORY_TAGS)}"}

    limit = min(limit, MAX_SEARCH_LIMIT)
    tag_filter = CATEGORY_TAGS[category]
    
    query = (
        f"[out:json][timeout:20];"
        f"("
        f"nwr{tag_filter}(around:{radius_m},{near_lat},{near_lon});"
        f");"
        f"out center {limit * 4};"
    )
    elements = query_overpass(query)

    places = []

    for el in elements:
        tags = el.get('tags', {})   
        name = tags.get('name')
        if not name:
            continue

        cuisine = tags.get("cuisine", "")
        if vegetarian and "vegetarian" not in cuisine and tags.get("diet:vegetarian") != "yes":
            continue
    
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")

        if lat is None or lon is None:
            continue

        places.append(
            {
                "name": name,
                "category": tags.get("tourism") or tags.get("amenity") or category,
                "cuisine": cuisine or None,
                "lat": lat,
                "lon": lon,
                "opening_hours": tags.get("opening_hours"),
                "source": f"osm:{el['type']}/{el['id']}",
            }
        )

        if len(places) >= limit:
            break

    return {"category": category, "count": len(places), "places": places}  
