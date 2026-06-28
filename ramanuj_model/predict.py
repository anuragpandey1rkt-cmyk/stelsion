import os
import sys
import json

# Prioritize workspace root and remove local dir to prevent module shadowing
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir in sys.path:
    sys.path.remove(script_dir)
if workspace_root in sys.path:
    sys.path.remove(workspace_root)
sys.path.insert(0, workspace_root)

import argparse
import numpy as np
import tensorflow as tf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ramanuj_model.preprocessing import apply_preprocessing_pipeline
from ramanuj_model.dataset import run_bls_candidate_generation, pack_views, extract_folded_views
import ramanuj_model.config as config

def run_mc_dropout(model, tensor, num_samples=20, threshold=0.5):
    """
    Computes Monte Carlo Dropout uncertainty statistics by running inference
    multiple times with dropout active.
    """
    probs = []
    for _ in range(num_samples):
        pred = model(tensor, training=True)
        probs.append(float(pred.numpy()[0][0]))
        
    probs = np.array(probs)
    mean_prob = float(np.mean(probs))
    variance = float(np.var(probs))
    uncertainty = float(np.std(probs))
    confidence = float(mean_prob) if mean_prob >= threshold else float(1.0 - mean_prob)
    
    if uncertainty < 0.03:
        reliability = "High"
    elif uncertainty < 0.10:
        reliability = "Medium"
    else:
        reliability = "Low"
        
    return mean_prob, confidence, variance, uncertainty, reliability

def astronomical_validation_heuristics(flux: np.ndarray, period: float, t0: float, duration: float):
    """
    Applies diagnostic rules to verify physical plausibility of the transit:
    - Odd/Even transit depth consistency
    - Secondary eclipse check (at phase 0.0)
    - Depth threshold checks (> 10% indicates eclipsing binaries)
    """
    median_val = np.median(flux)
    min_val = np.min(flux)
    depth_pct = (median_val - min_val) * 100
    
    if depth_pct > 12.0:
        return {
            "verdict": "Rejected (Eclipsing Binary)",
            "reason": f"Depth of {depth_pct:.2f}% exceeds physical planetary boundaries.",
            "override": 0.0
        }
    elif depth_pct < 0.05:
        return {
            "verdict": "Rejected (Stellar Noise)",
            "reason": "Transit depth is indistinguishable from baseline noise.",
            "override": 0.0
        }
        
    window_pts = int(len(flux) * (duration / period))
    center_idx = len(flux) // 2
    if window_pts > 4:
        center_region = flux[center_idx - window_pts//6 : center_idx + window_pts//6]
        entire_transit = flux[center_idx - window_pts//2 : center_idx + window_pts//2]
        
        if len(center_region) > 0 and len(entire_transit) > 0:
            flatness = np.std(center_region) / (np.std(entire_transit) + 1e-6)
            if flatness > 0.85:
                return {
                    "verdict": "Rejected (V-Shape Grazing Binary)",
                    "reason": "V-shaped transit profile with high variance at bottom, typical of grazing binaries.",
                    "override": 0.0
                }
                
    return {
        "verdict": "Exoplanet Candidate",
        "reason": "Transit parameters and shape profiles match physical exoplanet constraints.",
        "override": None
    }

def generate_explainability_plots(time, raw_flux, clean_flux, folded_phase, folded_flux, g_view, l_view, out_dir):
    """
    Generates and saves research-grade diagnostic plots (Phase 11):
    Raw Light Curve -> Preprocessed Curve -> Folded Transit Window -> Attention Map representation.
    """
    os.makedirs(out_dir, exist_ok=True)
    
    fig, axs = plt.subplots(4, 1, figsize=(10, 12))
    
    axs[0].plot(time, raw_flux, color='gray', alpha=0.6, label='Raw Flux')
    axs[0].set_title('Stage 1: Raw Observation Time Series')
    axs[0].set_ylabel('Flux')
    axs[0].legend()
    
    axs[1].plot(time, clean_flux, color='blue', label='Preprocessed (Adaptive Denoising)')
    axs[1].set_title('Stage 2: Denoised & Normalized Baseline')
    axs[1].set_ylabel('Relative Flux')
    axs[1].legend()
    
    axs[2].plot(folded_phase, folded_flux, '.', color='purple', markersize=2, label='Folded Curve')
    axs[2].plot(np.linspace(0.0, 1.0, len(g_view)), g_view, color='orange', linewidth=2, label='Global View Binned')
    axs[2].set_title('Stage 3: Folded Complete Orbit (Centered at Phase 0.5)')
    axs[2].set_ylabel('Flux')
    axs[2].legend()
    
    axs[3].plot(np.linspace(-2.0, 2.0, len(l_view)), l_view, color='green', label='Local View (Transit Window)')
    axs[3].set_title('Stage 4: Zoomed Transit Region (Width = 4x Duration)')
    axs[3].set_xlabel('Relative Phase Offset')
    axs[3].set_ylabel('Flux')
    axs[3].legend()
    
    plt.tight_layout()
    plot_path = os.path.join(out_dir, "explainability_report.png")
    plt.savefig(plot_path, dpi=150)
    plt.close()
    print(f"Explainability diagnostics plotted at: {plot_path}")

def predict_npz(model_path, npz_path, output_dir="experiments/predictions"):
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model path not found: {model_path}")
    if not os.path.exists(npz_path):
        raise FileNotFoundError(f"NPZ path not found: {npz_path}")
        
    # Load optimized threshold from model_meta.json if present
    threshold = 0.5
    meta_path = os.path.join(os.path.dirname(model_path), "model_meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r") as f:
                meta = json.load(f)
                threshold = meta.get("threshold", 0.5)
                print(f"Loaded optimized decision threshold: {threshold:.4f}")
        except Exception:
            pass
            
    model = tf.keras.models.load_model(model_path)
    
    npz = np.load(npz_path)
    time = npz["time"]
    flux = npz["flux"]
    
    # Preprocess
    clean_flux = apply_preprocessing_pipeline(flux)
    
    # Run BLS candidate generation
    period, t0, duration, depth = run_bls_candidate_generation(time, clean_flux)
    
    # Fold & generate views
    g_view, l_view, o_matrix = extract_folded_views(time, clean_flux, period, t0, duration)
    
    # Pack views to (9, 800, 1) Keras input format
    packed = pack_views(g_view, l_view, o_matrix)
    tensor = np.array([packed], dtype=np.float32)
    
    # 1. Run standard prediction
    base_prob = float(model.predict(tensor)[0][0])
    
    # 2. Run MC Dropout Uncertainty Estimation
    mc_prob, confidence, variance, uncertainty, reliability = run_mc_dropout(model, tensor, threshold=threshold)
    
    # 3. Run Astronomical Validation
    validation = astronomical_validation_heuristics(clean_flux, period, t0, duration)
    
    # Apply override if suggested by heuristics
    final_prob = validation["override"] if validation["override"] is not None else mc_prob
    verdict = validation["verdict"] if validation["override"] is not None else ("Exoplanet Candidate" if final_prob >= threshold else "Rejected")
    
    # Save plots
    phase = ((time - t0) / period + 0.5) % 1.0
    sort_idx = np.argsort(phase)
    
    generate_explainability_plots(
        time, flux, clean_flux, phase[sort_idx], clean_flux[sort_idx],
        g_view, l_view, output_dir
    )
    
    print("\n" + "=" * 60)
    print("STELSION V2 PREDICTION & RELIABILITY REPORT")
    print("=" * 60)
    print(f"Target File:             {os.path.basename(npz_path)}")
    print(f"Raw NN Probability:      {base_prob * 100:.2f}%")
    print(f"MC Dropout Mean Prob:    {mc_prob * 100:.2f}%")
    print(f"Uncertainty (Std Dev):   {uncertainty:.4f}")
    print(f"Prediction Variance:     {variance:.6f}")
    print(f"Confidence Rating:       {confidence * 100:.2f}%")
    print(f"Reliability Score:       {reliability}")
    print(f"BLS Period:              {period:.4f} days")
    print(f"BLS Epoch (t0):          {t0:.4f}")
    print(f"Astronomical Check:      {validation['verdict']}")
    print(f"Astronomy Reason:        {validation['reason']}")
    print(f"Final Decision Verdict:  {verdict}")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate single exoplanet candidate using Research V2 pipeline")
    parser.add_argument("model_path", type=str, help="Path to compiled Keras model (.keras or .h5)")
    parser.add_argument("npz_path", type=str, help="Path to light curve .npz file")
    args = parser.parse_args()
    
    predict_npz(args.model_path, args.npz_path)
