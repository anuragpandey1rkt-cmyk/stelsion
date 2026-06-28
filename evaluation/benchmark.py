import os
import sys
import time
import json
import csv
import argparse
import subprocess
from datetime import datetime
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, precision_recall_curve, confusion_matrix, ConfusionMatrixDisplay

# Ensure workspace root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from evaluation.metrics import calculate_metrics
from preprocessing.pipeline import PreprocessingPipeline

# ==========================================
# --- DATASET LOADER INTERFACE & IMPLEMENTATIONS ---
# ==========================================

class DatasetLoader:
    def load(self, directory: str):
        """
        Loads and returns (x_data, y_data) as numpy arrays.
        """
        raise NotImplementedError("Dataset loaders must implement the load method.")


class DefaultDatasetLoader(DatasetLoader):
    def load(self, directory: str):
        if not os.path.exists(directory):
            return None, None
            
        x_list, y_list = [], []
        
        # 1. Look for .npy files first
        npy_x_paths = [os.path.join(directory, f) for f in ["x_test.npy", "test_x.npy", "X_test.npy"]]
        npy_y_paths = [os.path.join(directory, f) for f in ["y_test.npy", "test_y.npy", "y_test.npy"]]
        
        x_file = next((p for p in npy_x_paths if os.path.exists(p)), None)
        y_file = next((p for p in npy_y_paths if os.path.exists(p)), None)
        
        if x_file and y_file:
            print(f"Loading dataset from NumPy files: {x_file}, {y_file}")
            return np.load(x_file), np.load(y_file)
            
        # 2. Look for JSON files in the folder
        json_files = [f for f in os.listdir(directory) if f.endswith(".json")]
        if json_files:
            print(f"Loading dataset from {len(json_files)} JSON files in {directory}...")
            for f in json_files:
                filepath = os.path.join(directory, f)
                with open(filepath, "r") as file_obj:
                    try:
                        data = json.load(file_obj)
                        if "flux" in data and "label" in data:
                            x_list.append(data["flux"])
                            y_list.append(data["label"])
                    except Exception:
                        pass
            if x_list:
                return np.array(x_list), np.array(y_list)
                
        # 3. Look for CSV files in the folder
        csv_files = [f for f in os.listdir(directory) if f.endswith(".csv")]
        if csv_files:
            print(f"Loading dataset from CSV files in {directory}...")
            for f in csv_files:
                filepath = os.path.join(directory, f)
                try:
                    data = np.genfromtxt(filepath, delimiter=",", skip_header=1)
                    if len(data.shape) > 1:
                        # Assuming last column is the label
                        x_list.extend(data[:, :-1].tolist())
                        y_list.extend(data[:, -1].tolist())
                except Exception:
                    pass
            if x_list:
                return np.array(x_list), np.array(y_list)
                
        return None, None


# ==========================================
# --- REPRODUCIBILITY & SYSTEM METADATA ---
# ==========================================

def get_git_info():
    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode("utf-8").strip()
    except Exception:
        git_commit = "N/A"
        
    try:
        git_user = subprocess.check_output(["git", "config", "user.name"]).decode("utf-8").strip()
    except Exception:
        git_user = "Unknown"
        
    return git_commit, git_user


# ==========================================
# --- MAIN BENCHMARK RUNNER ---
# ==========================================

def run_benchmark(model_path: str, developer_name: str = None):
    # Establish directories
    os.makedirs("experiments/plots", exist_ok=True)
    os.makedirs("datasets/test", exist_ok=True)
    os.makedirs("datasets/train", exist_ok=True)
    os.makedirs("datasets/validation", exist_ok=True)
    
    # 1. Load Test Dataset using DatasetLoader
    loader = DefaultDatasetLoader()
    x_test, y_test = loader.load("datasets/test")
    
    if x_test is None or len(x_test) == 0:
        print("[Error] No test dataset found in 'datasets/test/'.", file=sys.stderr)
        print("Please place test files (.json, .csv, or .npy) in 'datasets/test/' to run evaluation.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Successfully loaded test set with {len(x_test)} samples.")
    
    # 2. Load Model
    if not os.path.exists(model_path):
        print(f"[Error] Model path not found: {model_path}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Loading model from: {model_path}...")
    try:
        model = tf.keras.models.load_model(model_path)
    except Exception as e:
        print(f"[Error] Failed to load TensorFlow model: {e}", file=sys.stderr)
        sys.exit(1)
        
    # Get model parameters
    num_params = model.count_params()
    print(f"Model loaded successfully. Total parameters: {num_params:,}")
    
    # Get input shape details dynamically
    input_shape = model.input_shape
    if isinstance(input_shape, list):
        input_shape = input_shape[0]
    non_batch_dims = [d for d in input_shape if d is not None]
    total_elements = 1
    for d in non_batch_dims:
        total_elements *= d
        
    print(f"Detected model input shape: {input_shape} (requires {total_elements} flat elements)")
    
    # 3. Preprocess Test Data
    # Dynamically configure preprocessing to match model expected size
    pipeline = PreprocessingPipeline({
        'missing_value_method': 'interpolate',
        'normalization_method': 'median',
        'sigma_clipping_sigma': 3.0,
        'sigma_clipping_iters': 2,
        'wavelet_type': 'db4',
        'wavelet_level': 2,
        'sg_window': 15,
        'sg_polyorder': 2,
        'median_kernel': 5,
        'stellar_var_window': 101,
        'segment_length': total_elements,
        'enable_augmentation': False
    })
    
    print("Preprocessing test light curves...")
    processed_x = []
    for curve in x_test:
        clean = pipeline.process_single_curve(curve)
        padded = pipeline.segment_or_pad(clean, total_elements)
        processed_x.append(padded)
        
    # Reshape dynamically based on model's expected non-batch shape
    target_shape = [-1] + [d if d is not None else 1 for d in input_shape[1:]]
    test_tensor = np.array(processed_x, dtype=np.float32).reshape(target_shape)
    
    # 4. Inference and Timing
    print("Running model inference...")
    start_time = time.perf_counter()
    y_prob = model.predict(test_tensor)
    end_time = time.perf_counter()
    
    y_prob = y_prob.flatten()
    
    threshold = 0.5
    meta_paths = [
        os.path.join(os.path.dirname(model_path), "model_meta.json"),
        os.path.join(os.path.dirname(model_path), "..", "saved_models", "model_meta.json"),
        os.path.join(os.getcwd(), "saved_models", "model_meta.json")
    ]
    for p in meta_paths:
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    meta = json.load(f)
                    threshold = meta.get("threshold", 0.5)
                    print(f"Loaded optimized decision threshold: {threshold:.4f}")
                    break
            except Exception:
                pass
                
    y_pred = (y_prob >= threshold).astype(int)
    
    total_inference_time_ms = (end_time - start_time) * 1000.0
    inference_time_per_sample = total_inference_time_ms / len(x_test)
    print(f"Inference complete: total time {total_inference_time_ms:.2f} ms ({inference_time_per_sample:.4f} ms/sample)")
    
    # 5. Calculate Metrics
    metrics = calculate_metrics(y_test, y_pred, y_prob)
    
    # 6. Save Plots
    print("Generating evaluation plots...")
    # Confusion Matrix
    cm = confusion_matrix(y_test, y_pred, labels=[0, 1])
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=["Non-Planet", "Candidate"])
    disp.plot(cmap=plt.cm.Blues)
    plt.title(f"Confusion Matrix - {os.path.basename(model_path)}")
    plt.savefig("experiments/plots/confusion_matrix.png", dpi=150)
    plt.close()
    
    # ROC Curve
    fpr_roc, tpr_roc, _ = roc_curve(y_test, y_prob)
    plt.figure()
    plt.plot(fpr_roc, tpr_roc, label=f"ROC (AUC = {metrics['roc_auc']:.4f})")
    plt.plot([0, 1], [0, 1], 'k--')
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title(f'ROC Curve - {os.path.basename(model_path)}')
    plt.legend(loc="lower right")
    plt.savefig("experiments/plots/roc_curve.png", dpi=150)
    plt.close()
    
    # Precision-Recall Curve
    precision, recall, _ = precision_recall_curve(y_test, y_prob)
    plt.figure()
    plt.plot(recall, precision, label='Precision-Recall Curve')
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.title(f'Precision-Recall Curve - {os.path.basename(model_path)}')
    plt.legend(loc="lower left")
    plt.savefig("experiments/plots/precision_recall_curve.png", dpi=150)
    plt.close()
    
    # 7. Git & Environment logs
    git_commit, git_user = get_git_info()
    if developer_name is None:
        developer_name = git_user
        
    eval_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    python_ver = sys.version.split()[0]
    tf_ver = tf.__version__
    
    # 8. Log into Leaderboard CSV
    csv_file = "experiments/leaderboard.csv"
    headers = [
        "Model", "Developer", "Git Commit", "Date", "Python Version", "TF Version",
        "Accuracy", "Precision", "Recall", "F1 Score", "ROC-AUC",
        "False Positive Rate", "False Negative Rate", "Inference Time (ms/sample)",
        "Parameters"
    ]
    
    file_exists = os.path.exists(csv_file)
    with open(csv_file, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(headers)
            
        writer.writerow([
            os.path.basename(model_path),
            developer_name,
            git_commit,
            eval_date,
            python_ver,
            tf_ver,
            f"{metrics['accuracy']:.4f}",
            f"{metrics['precision']:.4f}",
            f"{metrics['recall']:.4f}",
            f"{metrics['f1_score']:.4f}",
            f"{metrics['roc_auc']:.4f}",
            f"{metrics['false_positive_rate']:.4f}",
            f"{metrics['false_negative_rate']:.4f}",
            f"{inference_time_per_sample:.4f}",
            num_params
        ])
        
    print("\n" + "=" * 50)
    print("EVALUATION RESULTS SUMMARY:")
    print("=" * 50)
    print(f"Model:                   {os.path.basename(model_path)}")
    print(f"Accuracy:                {metrics['accuracy']*100:.2f}%")
    print(f"Precision:               {metrics['precision']*100:.2f}%")
    print(f"Recall:                  {metrics['recall']*100:.2f}%")
    print(f"F1 Score:                {metrics['f1_score']:.4f}")
    print(f"ROC-AUC:                 {metrics['roc_auc']:.4f}")
    print(f"False Positive Rate:     {metrics['false_positive_rate']*100:.2f}%")
    print(f"False Negative Rate:     {metrics['false_negative_rate']*100:.2f}%")
    print(f"Inference Time:          {inference_time_per_sample:.4f} ms/sample")
    print("=" * 50)
    print(f"Results appended to {csv_file}")
    print("Plots saved under experiments/plots/")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="STELSION Shared Benchmark Evaluation Runner")
    parser.add_argument("model_path", type=str, help="Path to Keras model (.h5 or .keras or SavedModel directory)")
    parser.add_argument("--developer", type=str, default=None, help="Name of the developer (defaults to git config username)")
    args = parser.parse_args()
    
    run_benchmark(args.model_path, args.developer)
