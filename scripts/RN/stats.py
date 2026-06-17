import json
import pathlib

data = json.loads((pathlib.Path(__file__).parent / "repos.json").read_text())

total = len(data)
buildable = sum(1 for r in data if r.get("buildable"))

print(f"Total entries:  {total}")
print(f"Buildable:      {buildable}")
print(f"Not buildable:  {total - buildable}")
