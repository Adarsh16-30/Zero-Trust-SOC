import os
import torch
from fastapi import FastAPI, HTTPException
import uvicorn
from gnn_model import LateralMovementGNN, build_graph_from_neo4j

app = FastAPI(title="GNN Inference API")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "YourNeo4jPass123!")

# Initialize model
input_dim = 16
hidden_dim = 64
output_dim = 2
model = LateralMovementGNN(input_dim, hidden_dim, output_dim)
model.eval()

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/predict")
def predict():
    try:
        data = build_graph_from_neo4j(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        if data is None:
            return {"status": "no_data", "message": "No data found for inference."}
        
        with torch.no_grad():
            out = model(data.x, data.edge_index)
            preds = out.argmax(dim=1)
            
        anomalies = (preds == 1).sum().item()
        return {
            "status": "success",
            "total_nodes": data.num_nodes,
            "anomalies_detected": anomalies
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
