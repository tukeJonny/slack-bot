import sys
import json

json_obj = None
with open("../tokens.json", "r") as f:
	json_obj = json.load(f)

