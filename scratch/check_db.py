import httpx

r = httpx.post("http://localhost:8000/auth/login", json={"email": "demo@risklens.app", "password": "Demo1234!"})
if r.status_code != 200:
    print("Login failed:", r.status_code, r.text)
    exit(1)

token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}"}
res = httpx.get("http://localhost:8000/entries?limit=500", headers=h)
items = res.json().get("items", [])
print(f"Total entries for demo: {len(items)}")
cats = {}
for e in items:
    cat = e["category"]
    sub = e.get("subcategory")
    cats.setdefault(cat, []).append(sub)

for cat, subs in cats.items():
    print(f"  {cat}: {len(subs)} entries (sample subcategories: {set(subs[:5])})")

goals_res = httpx.get("http://localhost:8000/goals", headers=h)
print(f"Total goals: {len(goals_res.json().get('items', []))}")
