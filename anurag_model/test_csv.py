import sys
import os
import csv
import numpy as np
import tensorflow as tf

# Ensure parent directory is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anurag_model.architecture import UpgradedExoplanetDetectorNet
from anurag_model.pipeline import DualViewPipeline

# Configuration
CSV_PATH = "anurag_model/dummy_light_curve.csv"

def generate_dummy_csv():
    """Generates a dummy CSV light curve containing a simulated planet transit dip."""
    print(f"Creating a sample dummy CSV at: {CSV_PATH}")
    time = np.arange(2000)
    # Start with baseline flux around 1.0 with some noise
    flux = 1.0 + np.random.normal(0, 0.005, 2000)
    
    # Inject a 3% transit dip from step 800 to 900
    flux[800:900] -= 0.03
    
    # Save to CSV
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["time", "flux"])
        for t, val in zip(time, flux):
            writer.writerow([t, val])
    print("Dummy CSV generated successfully.")

def run_csv_inference():
    # Generate dummy if it doesn't exist
    if not os.path.exists(CSV_PATH):
        generate_dummy_csv()
        
    # Read the CSV
    print(f"Reading CSV file from: {CSV_PATH}...")
    flux_values = []
    with open(CSV_PATH, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        # Find flux column index
        flux_idx = 1 if "flux" in [h.lower() for h in header] else 0
        for row in reader:
            if row:
                flux_values.append(float(row[flux_idx]))
                
    print(f"Loaded {len(flux_values)} data points.")
    
    # Preprocess using the DualViewPipeline
    print("Running Dual-View Preprocessing Pipeline (Folding & Zooming)...")
    pipeline = DualViewPipeline()
    global_view, local_view, estimated_period, estimated_epoch = pipeline.process(flux_values)
    
    # Initialize model
    model = UpgradedExoplanetDetectorNet(input_len=2000)
    
    # Convert to NumPy arrays with batch and channel dimensions [Batch=1, SeqLen, Channels=1]
    global_tensor = global_view[np.newaxis, :, np.newaxis]
    local_tensor = local_view[np.newaxis, :, np.newaxis]
    
    # Run Inference
    print("Running model inference with Global and Local views...")
    probability, attention = model([global_tensor, local_tensor], training=False)
        
    prob = float(probability.numpy()[0][0])
    verdict = "Exoplanet Candidate" if prob >= 0.5 else "Rejected"
    
    # Estimate depth based on local view
    min_val = np.min(local_view)
    median_val = np.median(local_view)
    depth_percent = float(max(0.0, (median_val - min_val) * 100))
    
    # Parse Attention details
    mean_attn = tf.reduce_mean(attention[0], axis=0).numpy()
    max_attn_idx = int(np.argmax(mean_attn))
    approx_sequence_location = max_attn_idx * 32
    
    print("\n================ DUAL-VIEW DETECTOR REPORT ================")
    print(f"Model Classification Verdict: {verdict}")
    print(f"Exoplanet Candidate Probability: {prob * 100:.2f}%")
    print(f"Calculated Orbit Period (indices): {estimated_period:.1f}")
    print(f"Primary Transit Epoch (index): {estimated_epoch}")
    print(f"Estimated Transit Depth: {depth_percent:.2f}%")
    print(f"Global View Shape: {global_tensor.shape}")
    print(f"Local View Shape: {local_tensor.shape}")
    print(f"Attention Hotspot (phase sorted): Index {approx_sequence_location}")
    print("===========================================================")

if __name__ == "__main__":
    run_csv_inference()
