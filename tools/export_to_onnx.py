"""
Model Exporter: Scikit-Learn Pipeline to Web JSON
Exports the trained StandardScaler + GradientBoostingClassifier ensemble
with exact class alignment for zero-dependency edge TypeScript inference.
"""

import os
import json
import joblib
import numpy as np

def export_model_json(model_path: str, output_json_path: str, meta_path: str):
    print(f"[*] Loading model from {model_path}...")
    container = joblib.load(model_path)
    
    if isinstance(container, dict) and "model" in container:
        pipeline = container["model"]
        feature_names = container.get("features", [])
        version = container.get("version", "1.0")
    else:
        pipeline = container
        with open(meta_path, 'r') as f:
            meta = json.load(f)
        feature_names = meta.get("features", [])
        version = "1.0"
        
    scaler = pipeline.named_steps.get("scaler")
    classifier = pipeline.named_steps.get("classifier")
    
    # Scikit-Learn classes are alphabetical: e.g. ['malicious', 'safe', 'suspicious']
    classes = [str(c) for c in classifier.classes_.tolist()]
    print(f"[+] Actual model classes: {classes}")

    scaler_data = None
    if scaler is not None:
        scaler_data = {
            "mean": scaler.mean_.tolist(),
            "scale": scaler.scale_.tolist(),
            "var": scaler.var_.tolist()
        }
        print(f"[+] Extracted StandardScaler (means: {len(scaler_data['mean'])})")

    # Extract Gradient Boosting Trees
    n_estimators = classifier.estimators_.shape[0]
    n_classes = classifier.estimators_.shape[1] if len(classifier.estimators_.shape) > 1 else 1
    print(f"[+] Estimators shape: {classifier.estimators_.shape} (n_estimators={n_estimators}, n_classes={n_classes})")
    
    trees_data = []
    for i in range(n_estimators):
        stage_trees = []
        for c in range(n_classes):
            tree = classifier.estimators_[i, c].tree_ if len(classifier.estimators_.shape) > 1 else classifier.estimators_[i].tree_
            tree_dict = {
                "children_left": tree.children_left.tolist(),
                "children_right": tree.children_right.tolist(),
                "feature": tree.feature.tolist(),
                "threshold": tree.threshold.tolist(),
                "value": tree.value.squeeze().tolist(),
            }
            stage_trees.append(tree_dict)
        trees_data.append(stage_trees)
        
    # Extract prior / init value
    init_prior = [0.0] * len(classes)
    if hasattr(classifier, "init_") and hasattr(classifier.init_, "prior"):
        init_prior = classifier.init_.prior.tolist()
    elif hasattr(classifier, "init_") and hasattr(classifier.init_, "class_prior_"):
        init_prior = np.log(classifier.init_.class_prior_).tolist()

    export_data = {
        "version": version,
        "model_type": "GradientBoostingClassifier",
        "learning_rate": float(classifier.learning_rate),
        "init_prior": init_prior,
        "scaler": scaler_data,
        "features": feature_names,
        "classes": classes,
        "trees": trees_data
    }
    
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
    with open(output_json_path, 'w') as f:
        json.dump(export_data, f)
        
    print(f"[SUCCESS] Exported ensemble model to {output_json_path} ({os.path.getsize(output_json_path)} bytes)")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model_file = os.path.join(base_dir, "models", "keylogger_detector.joblib")
    meta_file = os.path.join(base_dir, "models", "keylogger_detector.json")
    web_model_file = os.path.join(base_dir, "web", "public", "models", "keylogger_detector.json")
    
    export_model_json(model_file, web_model_file, meta_file)
