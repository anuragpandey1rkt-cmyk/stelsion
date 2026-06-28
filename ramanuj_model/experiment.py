import os
import json
import csv
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import (
    roc_curve, precision_recall_curve, confusion_matrix,
    ConfusionMatrixDisplay, classification_report
)
import ramanuj_model.config as config
from ramanuj_model.utils import get_system_metadata

def create_experiment_dir():
    """
    Finds the next incremental run number (e.g. 001_baseline_combined)
    and initializes its folder structure under ramanuj_model/experiments/
    """
    os.makedirs(config.EXPERIMENTS_DIR, exist_ok=True)
    existing_dirs = [
        d for d in os.listdir(config.EXPERIMENTS_DIR) 
        if os.path.isdir(os.path.join(config.EXPERIMENTS_DIR, d))
    ]
    
    next_idx = 1
    for d in existing_dirs:
        try:
            parts = d.split("_")
            idx = int(parts[0])
            if idx >= next_idx:
                next_idx = idx + 1
        except ValueError:
            pass
            
    dir_name = f"{next_idx:03d}_{config.ARCHITECTURE}_{config.PREPROCESSING}"
    exp_dir = os.path.join(config.EXPERIMENTS_DIR, dir_name)
    os.makedirs(exp_dir, exist_ok=True)
    os.makedirs(os.path.join(exp_dir, "plots"), exist_ok=True)
    return exp_dir

def calculate_per_class_metrics(y_true, y_pred):
    """
    Computes Precision, Recall, and F1-score for class 1 (Transit) and class 0 (Non-Transit).
    """
    report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
    
    transit_key = '1.0' if '1.0' in report else '1'
    non_transit_key = '0.0' if '0.0' in report else '0'
    
    transit_metrics = report.get(transit_key, {})
    non_transit_metrics = report.get(non_transit_key, {})
    
    return {
        "transit_precision": transit_metrics.get("precision", 0.0),
        "transit_recall": transit_metrics.get("recall", 0.0),
        "transit_f1": transit_metrics.get("f1-score", 0.0),
        "non_transit_precision": non_transit_metrics.get("precision", 0.0),
        "non_transit_recall": non_transit_metrics.get("recall", 0.0)
    }

def save_experiment_results(exp_dir, model, history, val_metrics, config_overrides=None,
                            y_val_true=None, y_val_prob=None, threshold=0.5, best_epoch=1,
                            elapsed_time=0.0, train_size=0, val_size=0, pos_size=0, neg_size=0):
    """
    Persists configuration parameters, metrics, plots, and a consolidated markdown report.
    """
    # 1. Save model in native Keras format
    model.save(os.path.join(exp_dir, "model.keras"))
    
    # 2. Save configuration parameters
    cfg_dict = {
        "ARCHITECTURE": config.ARCHITECTURE,
        "PREPROCESSING": config.PREPROCESSING,
        "INPUT_SHAPE": config.INPUT_SHAPE,
        "BATCH_SIZE": config.BATCH_SIZE,
        "EPOCHS": config.EPOCHS,
        "LEARNING_RATE": config.LEARNING_RATE,
        "LOSS": config.LOSS,
        "OPTIMIZER": config.OPTIMIZER,
        "WEIGHT_DECAY": config.WEIGHT_DECAY,
        "SEED": config.SEED,
        "ENABLE_KFOLD": config.ENABLE_KFOLD,
        "NUM_FOLDS": config.NUM_FOLDS
    }
    if config_overrides:
        cfg_dict.update(config_overrides)
        
    with open(os.path.join(exp_dir, "config.json"), "w") as f:
        json.dump(cfg_dict, f, indent=4)
        
    # 3. Save validation metrics
    with open(os.path.join(exp_dir, "metrics.json"), "w") as f:
        json.dump(val_metrics, f, indent=4)
        
    # 4. Save history as CSV
    if hasattr(history, 'history') and history.history:
        hist_df = pd.DataFrame(history.history)
        hist_df.to_csv(os.path.join(exp_dir, "history.csv"), index=False)
        
    # 5. Generate and save plots and calculate per-class metrics
    per_class = {}
    fps, fns = [], []
    
    if y_val_true is not None and y_val_prob is not None:
        y_val_pred = (y_val_prob >= threshold).astype(int)
        
        # Calculate per-class metrics
        per_class = calculate_per_class_metrics(y_val_true, y_val_pred)
        
        # Identify False Positives and False Negatives examples
        for i in range(len(y_val_true)):
            true_l = int(y_val_true[i])
            pred_l = int(y_val_pred[i])
            prob = float(y_val_prob[i])
            if true_l == 0 and pred_l == 1:
                fps.append((i, prob))
            elif true_l == 1 and pred_l == 0:
                fns.append((i, prob))
                
        # Confusion Matrix
        cm = confusion_matrix(y_val_true, y_val_pred, labels=[0, 1])
        disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=["Non-Planet", "Candidate"])
        disp.plot(cmap=plt.cm.Blues)
        plt.title(f"Validation Confusion Matrix (Threshold={threshold:.2f})")
        plt.savefig(os.path.join(exp_dir, "plots", "confusion_matrix.png"), dpi=150)
        plt.close()
        
        # ROC Curve
        fpr, tpr, _ = roc_curve(y_val_true, y_val_prob)
        plt.figure()
        plt.plot(fpr, tpr, label=f"ROC (AUC = {val_metrics.get('roc_auc', 0.5):.4f})")
        plt.plot([0, 1], [0, 1], 'k--')
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel('False Positive Rate')
        plt.ylabel('True Positive Rate')
        plt.title('Validation ROC Curve')
        plt.legend(loc="lower right")
        plt.savefig(os.path.join(exp_dir, "plots", "roc_curve.png"), dpi=150)
        plt.close()
        
        # Precision-Recall Curve
        precision, recall, _ = precision_recall_curve(y_val_true, y_val_prob)
        plt.figure()
        plt.plot(recall, precision, label='Precision-Recall Curve')
        plt.xlabel('Recall')
        plt.ylabel('Precision')
        plt.title('Validation Precision-Recall Curve')
        plt.savefig(os.path.join(exp_dir, "plots", "precision_recall_curve.png"), dpi=150)
        plt.close()
        
        # Prediction Probability Histogram
        plt.figure()
        plt.hist(y_val_prob[y_val_true == 1.0], bins=10, alpha=0.5, label='Transits (Positives)', color='orange')
        plt.hist(y_val_prob[y_val_true == 0.0], bins=10, alpha=0.5, label='Non-Transits (Negatives)', color='blue')
        plt.axvline(threshold, color='red', linestyle='--', label=f'Threshold ({threshold:.2f})')
        plt.xlabel('Predicted Probability')
        plt.ylabel('Count')
        plt.title('Probability Distribution Histogram')
        plt.legend(loc='upper center')
        plt.savefig(os.path.join(exp_dir, "plots", "probability_histogram.png"), dpi=150)
        plt.close()
        
    # Get system metadata for reproducibility
    sys_meta = get_system_metadata()
    
    # 6. Generate rich markdown report
    report_content = f"""# STELSION V3 Experiment Report - Run {os.path.basename(exp_dir)}

## Meta Information & Reproducibility
- **Model Architecture**: {cfg_dict['ARCHITECTURE']}
- **Total Parameters**: {model.count_params():,}
- **Dataset Size**: {train_size + val_size} (Train: {train_size}, Validation: {val_size})
- **Class Distribution**: {pos_size} Positives, {neg_size} Negatives
- **Training Time**: {elapsed_time:.2f} seconds
- **Best Epoch**: {best_epoch}
- **Optimal Threshold**: **{threshold:.4f}**
- **Git Commit**: {sys_meta.get('git_commit', 'Unknown')}
- **TensorFlow Version**: {sys_meta.get('tensorflow_version', 'Unknown')}
- **Python Version**: {sys_meta.get('python_version', 'Unknown')}
- **Random Seed**: {cfg_dict['SEED']}

## Validation Metrics Summary
- **Accuracy**: {val_metrics.get('accuracy', 0.0)*100:.2f}%
- **Precision**: {val_metrics.get('precision', 0.0):.4f}
- **Recall**: {val_metrics.get('recall', 0.0):.4f}
- **F1 Score**: **{val_metrics.get('f1_score', 0.0):.4f}**
- **ROC-AUC**: {val_metrics.get('roc_auc', 0.5):.4f}

## Per-Class Metrics
- **Transit Precision**: {per_class.get('transit_precision', 0.0):.4f}
- **Transit Recall**: {per_class.get('transit_recall', 0.0):.4f}
- **Transit F1**: {per_class.get('transit_f1', 0.0):.4f}
- **Non-Transit Precision**: {per_class.get('non_transit_precision', 0.0):.4f}
- **Non-Transit Recall**: {per_class.get('non_transit_recall', 0.0):.4f}

## Error Analysis (Validation Set Examples)
- **False Positives ({len(fps)} examples)**: {', '.join([f"idx {i} (prob {p:.3f})" for i, p in fps[:10]])}
- **False Negatives ({len(fns)} examples)**: {', '.join([f"idx {i} (prob {p:.3f})" for i, p in fns[:10]])}

## Evaluation Curves
### Confusion Matrix
![Confusion Matrix](plots/confusion_matrix.png)

### ROC Curve
![ROC Curve](plots/roc_curve.png)

### Precision-Recall Curve
![PR Curve](plots/precision_recall_curve.png)

### Probability Histogram
![Histogram](plots/probability_histogram.png)
"""
    # Write to local run folder
    with open(os.path.join(exp_dir, "notes.md"), "w") as f:
        f.write(report_content)
        
    # Write to experiments/latest_report.md
    latest_report_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "experiments", "latest_report.md"))
    os.makedirs(os.path.dirname(latest_report_path), exist_ok=True)
    with open(latest_report_path, "w") as f:
        f.write(report_content)
        
    print(f"All experiment files saved successfully to: {exp_dir}")
    print(f"Consolidated latest report saved to: {latest_report_path}")
