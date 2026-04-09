import torch
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv
from torch_geometric.data import Data
from neo4j import GraphDatabase
import os

class LateralMovementGNN(torch.nn.Module):
    def __init__(self, input_dim: int = 16, hidden_dim: int = 64, output_dim: int = 2):
        super().__init__()
        self.conv1 = SAGEConv(input_dim, hidden_dim)
        self.conv2 = SAGEConv(hidden_dim, hidden_dim)
        self.conv3 = SAGEConv(hidden_dim, output_dim)

    def forward(self, x, edge_index):
        x = F.relu(self.conv1(x, edge_index))
        x = F.dropout(x, p=0.2, training=self.training)
        x = F.relu(self.conv2(x, edge_index))
        x = self.conv3(x, edge_index)
        return F.log_softmax(x, dim=1)

def build_graph_from_neo4j(neo4j_uri: str, neo4j_user: str, neo4j_password: str, time_window_hours: int = 24) -> Data:
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User)-[r:LOGGED_INTO]->(m:Machine)
            WHERE r.timestamp > datetime() - duration({hours: $hours})
            RETURN u.id AS user_id, m.id AS machine_id, r.success AS success, r.privilege_level AS priv
            LIMIT 50000
        """, hours=time_window_hours)
        records = list(result)

    if not records:
        print("[WARN] No auth records found in Neo4j for the GNN model.")
        return None

    nodes = {}
    edges = [[], []]
    for rec in records:
        uid, mid = f"user:{rec['user_id']}", f"machine:{rec['machine_id']}"
        if uid not in nodes: nodes[uid] = len(nodes)
        if mid not in nodes: nodes[mid] = len(nodes)
        edges[0].append(nodes[uid]); edges[1].append(nodes[mid])

    x = torch.zeros((len(nodes), 16))
    for node_name, idx in nodes.items():
        x[idx, 0] = 1.0 if node_name.startswith("user:") else 0.0
        x[idx, 1] = 1.0 if node_name.startswith("machine:") else 0.0

    return Data(x=x, edge_index=torch.tensor(edges, dtype=torch.long))

if __name__ == "__main__":
    print("GNN Lateral Movement Model loaded.")
