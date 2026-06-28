import os
import json
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from astropy.timeseries import BoxLeastSquares
from ramanuj_model.preprocessing import apply_preprocessing_pipeline
import ramanuj_model.config as config

def run_bls_candidate_generation(time: np.ndarray, flux: np.ndarray):
    """
    Runs Box Least Squares (BLS) periodogram search on a light curve
    to estimate candidate transit parameters.
    """
    try:
        min_p = config.BLS_MIN_PERIOD
        max_p = min(config.BLS_MAX_PERIOD, (np.max(time) - np.min(time)) / 2.0)
        if max_p <= min_p:
            max_p = min_p + 5.0
            
        bls = BoxLeastSquares(time, flux)
        durations = np.linspace(0.04, 0.2, 5)
        period_grid = np.linspace(min_p, max_p, 1000)
        power_results = bls.power(period_grid, durations)
        
        best_idx = np.argmax(power_results.power)
        period = float(power_results.period[best_idx])
        t0 = float(power_results.transit_time[best_idx])
        duration = float(power_results.duration[best_idx])
        depth = float(power_results.depth[best_idx])
    except Exception:
        # Fallback values
        period = 10.0
        t0 = np.min(time) + 2.0
        duration = 0.1
        depth = 0.01
        
    return period, t0, duration, depth

def extract_folded_views(time: np.ndarray, flux: np.ndarray, period: float, t0: float, duration: float):
    """
    Generates three representation views from the folded light curve:
    1. Global View (2000 bins)
    2. Local View (200 bins)
    3. Orbit Matrix (10 x 500 = 5000 elements)
    """
    phase = ((time - t0) / period + 0.5) % 1.0
    sort_idx = np.argsort(phase)
    folded_phase = phase[sort_idx]
    folded_flux = flux[sort_idx]
    
    # 2. Global View: interpolate complete orbit to 2000 points
    global_grid = np.linspace(0.0, 1.0, config.GLOBAL_VIEW_LEN)
    global_view = np.interp(global_grid, folded_phase, folded_flux)
    
    # 3. Local View: extract transit window (4 * duration) centered at phase 0.5
    local_width = 4.0 * (duration / period)
    local_start = max(0.0, 0.5 - local_width / 2.0)
    local_end = min(1.0, 0.5 + local_width / 2.0)
    
    local_grid = np.linspace(local_start, local_end, config.LOCAL_VIEW_LEN)
    local_view = np.interp(local_grid, folded_phase, folded_flux)
    
    # 4. Orbit Matrix: segment by individual orbits (shape 10 x 500 = 5000 elements)
    num_orbits = 10
    num_bins = 500
    t_start, t_end = np.min(time), np.max(time)
    
    start_orb = int(np.floor((t_start - t0) / period))
    end_orb = int(np.ceil((t_end - t0) / period))
    
    orbits = []
    for i in range(start_orb, end_orb):
        orb_t_start = t0 + (i - 0.5) * period
        orb_t_end = t0 + (i + 0.5) * period
        
        mask = (time >= orb_t_start) & (time < orb_t_end)
        t_orb = time[mask]
        f_orb = flux[mask]
        
        if len(t_orb) > 5:
            p_orb = (t_orb - orb_t_start) / period
            s_idx = np.argsort(p_orb)
            
            grid_orb = np.linspace(0.0, 1.0, num_bins)
            binned = np.interp(grid_orb, p_orb[s_idx], f_orb[s_idx])
            orbits.append(binned)
            
    if len(orbits) == 0:
        orbits = [np.zeros(num_bins) for _ in range(num_orbits)]
        
    if len(orbits) < num_orbits:
        padding = [np.zeros(num_bins) for _ in range(num_orbits - len(orbits))]
        orbits.extend(padding)
    elif len(orbits) > num_orbits:
        orbits = orbits[:num_orbits]
        
    orbit_matrix = np.array(orbits, dtype=np.float32)
    
    return global_view, local_view, orbit_matrix

def pack_views(global_view, local_view, orbit_matrix):
    """
    Concatenates global, local, and matrix views into a single flat array
    of length 7200 and reshapes it to (9, 800, 1).
    """
    packed = np.concatenate([
        global_view.flatten(),
        local_view.flatten(),
        orbit_matrix.flatten()
    ])
    return packed.reshape(9, 800, 1)

def prepare_datasets():
    """
    Loads all .npz Kepler light curves listed in dataset_index.csv.
    Applies adaptive preprocessing, runs BLS periodograms, folds, splits,
    balances, and exports test files for shared auto-benchmarking.
    """
    index_path = "dataset_index.csv"
    if not os.path.exists(index_path):
        raise FileNotFoundError(f"dataset_index.csv not found. Run dataset_fetcher.py first.")
        
    df = pd.read_csv(index_path)
    # Remove duplicates by KIC ID (kepid)
    df = df.drop_duplicates(subset=["kepid"])
    
    # Map labels: confirmed planet or candidate -> 1.0, others -> 0.0
    df["numeric_label"] = df["label"].apply(
        lambda l: 1.0 if str(l).strip().lower() in ["transit", "candidate"] else 0.0
    )
    
    # Stratified Splits at index level (70% Train, 15% Validation, 15% Test)
    train_df, temp_df = train_test_split(
        df, test_size=0.3, random_state=config.SEED, stratify=df["numeric_label"]
    )
    val_df, test_df = train_test_split(
        temp_df, test_size=0.5, random_state=config.SEED, stratify=temp_df["numeric_label"]
    )
    
    print("\n" + "=" * 50)
    print("DATASET INDEX-LEVEL SPLITS (PRE-INGESTION)")
    print("=" * 50)
    print(f"Total Unique Catalog Samples: {len(df)}")
    print(f"Train split:       {len(train_df)} targets")
    print(f"Validation split:  {len(val_df)} targets")
    print(f"Test split:        {len(test_df)} targets")
    print("=" * 50 + "\n")
    
    from ramanuj_model.augmentation import generate_augmentations
    
    def process_split(split_df, augment=False):
        x_packed = []
        labels = []
        kepids = []
        
        for _, row in split_df.iterrows():
            file_path = row["file"]
            kepid = row["kepid"]
            label = row["numeric_label"]
            
            if not os.path.exists(file_path):
                continue
                
            try:
                npz = np.load(file_path)
                time = npz["time"]
                flux = npz["flux"]
                
                # Remove NaNs from raw input
                nan_mask = np.isnan(time) | np.isnan(flux)
                time = time[~nan_mask]
                flux = flux[~nan_mask]
                
                if len(flux) < 50:
                    continue
                    
                # Apply configurable preprocessing
                clean_flux = apply_preprocessing_pipeline(flux)
                
                # Augment only training transit candidates
                count = 2 if (label == 1.0 and augment) else 0
                variants = generate_augmentations(time, clean_flux, count=count)
                
                for t_v, f_v in variants:
                    # Run BLS candidate generation
                    period, t0, duration, depth = run_bls_candidate_generation(t_v, f_v)
                    # Fold and extract representation views
                    g_view, l_view, o_matrix = extract_folded_views(t_v, f_v, period, t0, duration)
                    # Pack views
                    packed_sample = pack_views(g_view, l_view, o_matrix)
                    
                    x_packed.append(packed_sample)
                    labels.append(label)
                    kepids.append(kepid)
            except Exception:
                pass
                
        return np.array(x_packed, dtype=np.float32), np.array(labels, dtype=np.float32), np.array(kepids, dtype=np.int32)
        
    print("Processing Train Split...")
    x_train, y_train, _ = process_split(train_df, augment=config.ENABLE_TRAIN_AUGMENTATION)
    
    print("Processing Validation Split...")
    x_val, y_val, _ = process_split(val_df, augment=False)
    
    print("Processing Test Split...")
    x_test, y_test, test_kepids = process_split(test_df, augment=False)
    
    # Save test dataset split to datasets/test/ for shared benchmark evaluation
    os.makedirs("datasets/test", exist_ok=True)
    # Clean previous JSON files to avoid pollution
    for f in os.listdir("datasets/test"):
        if f.endswith(".json"):
            try:
                os.remove(os.path.join("datasets/test", f))
            except Exception:
                pass
                
    for idx in range(len(y_test)):
        k_id = test_kepids[idx]
        lbl = int(y_test[idx])
        flat_flux = x_test[idx].flatten()
        test_file = os.path.join("datasets/test", f"KIC_{k_id}.json")
        with open(test_file, "w") as f:
            json.dump({
                "flux": flat_flux.tolist(),
                "label": lbl,
                "candidate": f"KIC {k_id}"
            }, f)
            
    print("\n" + "=" * 50)
    print("PROCESSED DATASET SIZE DETAILS")
    print("=" * 50)
    print(f"Train set:       {len(y_train)} samples (Positive: {np.sum(y_train == 1.0)}, Negative: {np.sum(y_train == 0.0)})")
    print(f"Validation set:  {len(y_val)} samples (Positive: {np.sum(y_val == 1.0)}, Negative: {np.sum(y_val == 0.0)})")
    print(f"Test set:        {len(y_test)} samples (Positive: {np.sum(y_test == 1.0)}, Negative: {np.sum(y_test == 0.0)})")
    print("=" * 50 + "\n")
    
    return (x_train, y_train), (x_val, y_val), (x_test, y_test)
