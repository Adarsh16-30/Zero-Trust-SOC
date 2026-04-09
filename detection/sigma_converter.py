import yaml
import os
import json

class SigmaConverter:
    def __init__(self, rules_path):
        self.rules_path = rules_path
        self.rules = []
        self.load_rules()

    def load_rules(self):
        for root, _, files in os.walk(self.rules_path):
            for file in files:
                if file.endswith(".yml") or file.endswith(".yaml"):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            docs = list(yaml.safe_load_all(f))
                    except UnicodeDecodeError:
                        # Fallback for unexpected legacy-encoded files.
                        try:
                            with open(file_path, "r", encoding="latin-1") as f:
                                docs = list(yaml.safe_load_all(f))
                        except Exception as e:
                            print(f"Error loading rule {file}: {e}")
                            continue
                    except Exception as e:
                        print(f"Error loading rule {file}: {e}")
                        continue

                    for rule in docs:
                        if isinstance(rule, dict):
                            self.rules.append(rule)

    def convert_to_filters(self):
        filters = []
        for rule in self.rules:
            if not isinstance(rule, dict):
                continue
            status = rule.get("status", "")
            if status in ["deprecated", "unsupported"]:
                continue

            detection = rule.get("detection", {})
            selection = detection.get("selection", {})

            if not selection:
                continue

            rule_filter = {
                "id": rule.get("title", rule.get("id", "unknown")),
                "level": rule.get("level", "informational"),
                "tags": rule.get("tags", []),
                "conditions": selection
            }
            filters.append(rule_filter)
        return filters

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    rules_dir = os.path.join(base_dir, "sigma-rules")
    output_file = os.path.join(base_dir, "flink-config", "active_rules.json")
    
    # Ensure output dir exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    converter = SigmaConverter(rules_dir)
    filters = converter.convert_to_filters()
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(filters, f, indent=2)
    print(f"Converted {len(filters)} rules to Flink config at {output_file}.")
