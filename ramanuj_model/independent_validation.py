import tensorflow as tf
import os
import sys

# Prioritize workspace root and remove local dir to prevent module shadowing
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir in sys.path:
    sys.path.remove(script_dir)
if workspace_root in sys.path:
    sys.path.remove(workspace_root)
sys.path.insert(0, workspace_root)

# Ensure workspace root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd
from lightkurve import search_lightcurve

import ramanuj_model.config as config
from ramanuj_model.predict import predict_npz

def download_unseen_targets():
    print("=" * 60)
    print("INDEPENDENT EXOPLANET VALIDATION")
    print("=" * 60)
    
    # 1. Load the cumulative catalog and the training index
    koi = pd.read_csv("modified datasets/koi_cumulative_labeled.csv", comment='#')
    trained_index = pd.read_csv("dataset_index.csv")
    trained_kepids = set(trained_index["kepid"].unique())
    
    # Filter catalog for candidates not in training set
    unseen_koi = koi[~koi["kepid"].isin(trained_kepids)]
    
    # Pick 2 confirmed transits (exoplanets) and 2 false positives
    positives = unseen_koi[unseen_koi["signal_class"] == "transit"].head(2)
    negatives = unseen_koi[unseen_koi["signal_class"] == "stellar_eclipse"].head(2)
    
    os.makedirs("unseen_dataset", exist_ok=True)
    downloaded_records = []
    
    for _, row in pd.concat([positives, negatives]).iterrows():
        kepid = row["kepid"]
        label = row["signal_class"]
        
        print(f"Downloading unseen target KIC {kepid} ({label})...")
        try:
            lc = search_lightcurve(f"KIC {kepid}", mission="kepler").download()
            lc = lc.remove_nans()
            lc = lc.normalize()
            
            filepath = f"unseen_dataset/{kepid}.npz"
            np.savez(
                filepath,
                time=lc.time.value,
                flux=lc.flux.value
            )
            downloaded_records.append({
                "kepid": kepid,
                "label": label,
                "file": filepath
            })
        except Exception as e:
            print(f"  Failed to download KIC {kepid}: {e}")
            
    print("\nStarting prediction runs on unseen targets:")
    model_path = os.path.join(config.SAVED_MODELS_DIR, f"{config.ARCHITECTURE}_model.h5")
    
    for record in downloaded_records:
        print(f"\n--- Testing KIC {record['kepid']} (Label: {record['label']}) ---")
        predict_npz(model_path, record["file"], output_dir="experiments/predictions_unseen")
        
    print("=" * 60)

if __name__ == "__main__":
    download_unseen_targets()
