import os
import json
import numpy as np
import requests
import joblib
from requests.auth import HTTPBasicAuth
from sklearn.ensemble import IsolationForest

def fetch_data():
    OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "opensearch:9200")
    OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", "admin")
    OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD")
    if not OPENSEARCH_PASSWORD:
        raise SystemExit("[ERROR] OPENSEARCH_PASSWORD env var not set.")
    
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    X_train = []
    try:
        url = f"https://{OPENSEARCH_HOST}/_search"
        query = {"size": 5000, "query": {"match_all": {}}}
        print(f"Fetching from {url}")
        resp = requests.post(url, json=query, auth=HTTPBasicAuth(OPENSEARCH_USER, OPENSEARCH_PASSWORD), verify=False)
        if resp.status_code == 200:
            hits = resp.json().get("hits", {}).get("hits", [])
            for h in hits:
                payload = h.get("_source", {}).get("log", h.get("_source", {}).get("full_log", ""))
                if payload:
                    f1 = len(payload)
                    f2 = len(set(payload)) / (len(payload) + 1)
                    X_train.append([f1, f2])
    except Exception as e:
        print(f"Error fetching: {e}")
        
        print("[ERROR] No training data found in OpenSearch. Collect real events first (run the stack for at least 10 minutes), then re-run train.py.")
        raise SystemExit(1)
    
    if not X_train:
        raise SystemExit("[ERROR] No log/full_log fields found in OpenSearch events.")
    return np.array(X_train)

if __name__ == "__main__":
    X_train = fetch_data()
    model = IsolationForest(contamination=0.01)
    model.fit(X_train)
    model_path = os.getenv("MODEL_PATH", "/app/model.pkl")
    joblib.dump(model, model_path)
    print(f"Model trained and saved to {model_path}")
