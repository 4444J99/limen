import json
import urllib.request
import urllib.error
import os
import concurrent.futures
import time

def get_api_key():
    env_path = os.path.expanduser('~/.limen.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('export GEMINI_API_KEY='):
                    return line.split('=', 1)[1].strip().strip('"\'')
    return os.environ.get('GEMINI_API_KEY')

api_key = get_api_key()  # allow-secret

API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

def enrich_lever(lever):
    prompt = f"""You are analyzing a manual administrative or technical action that a human has to take.
Here is the raw data for the lever:
ID: {lever.get('id')}
Label: {lever.get('label')}
Note: {lever.get('note')}

Respond with a raw JSON object containing exactly these three keys:
"pros": A short 1-2 sentence description of the pros/benefits of doing this now.
"cons": A short 1-2 sentence description of the cons/risks/costs of doing this now.
"paths": An array of strings representing 2-4 concrete choices the user could make (e.g. "Execute Now", "Delegate to an Agent", "Dismiss/Discharge", "Defer for 30 Days").
Only return the raw JSON object.
"""
    data = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
    }).encode('utf-8')
    
    req = urllib.request.Request(API_URL, data=data, headers={'Content-Type': 'application/json'})
    
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
                text = result['candidates'][0]['content']['parts'][0]['text']
                parsed = json.loads(text.strip())
                lever['pros'] = parsed.get('pros', '')
                lever['cons'] = parsed.get('cons', '')
                lever['paths'] = parsed.get('paths', [])
                return lever
        except Exception as e:
            print(f"Error on {lever.get('id')}: {e}")
            if hasattr(e, 'read'):
                print(e.read().decode())
            time.sleep(1)
            
    lever['pros'] = "Failed to generate pros."
    lever['cons'] = "Failed to generate cons."
    lever['paths'] = ["Execute Now", "Dismiss", "Defer"]
    return lever

def main():
    print("Loading levers...")
    with open("his-hand-levers.json", "r") as f:
        data = json.load(f)
    
    levers = data.get("levers", [])
    open_levers = [lv for lv in levers if lv.get("status", "open").lower() in ("open", "", "needs_human")]
    
    print(f"Enriching {len(open_levers)} open levers using Gemini API...")
    enriched = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(enrich_lever, lv): lv for lv in open_levers}
        for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
            enriched.append(future.result())
            if idx % 10 == 0:
                print(f"Processed {idx}/{len(open_levers)}")
                
    for i, lv in enumerate(levers):
        if lv.get("status", "open").lower() in ("open", "", "needs_human"):
            for elv in enriched:
                if elv['id'] == lv['id']:
                    levers[i] = elv
                    break
                    
    data["levers"] = levers
    with open("his-hand-levers-enriched.json", "w") as f:
        json.dump(data, f, indent=2)
    print("Done!")

if __name__ == "__main__":
    main()
