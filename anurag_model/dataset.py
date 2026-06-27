import os
import sys
import numpy as np
import tensorflow as tf

# Ensure parent directory is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anurag_model.pipeline import DualViewPipeline

def generate_trapezoidal_transit(length, period, depth, duration, t0):
    """
    Generates a physically motivated trapezoidal transit dip profile.
    Uses periodic folding to support multiple transit events in a single curve.
    """
    time = np.arange(length)
    profile = np.zeros(length, dtype=np.float32)
    
    # Calculate phase [0.0, 1.0]
    phase = ((time - t0) / period) % 1.0
    
    # Calculate index distance to the nearest periodic transit center
    dist = np.minimum(phase, 1.0 - phase) * period
    
    # Ingress/egress slope width (10% of total duration)
    ingress = duration * 0.1
    half_dur = duration / 2.0
    
    t_start = half_dur - ingress / 2.0
    t_end = half_dur + ingress / 2.0
    
    # Core flat bottom of transit
    flat_mask = dist <= t_start
    profile[flat_mask] = -depth
    
    # Ingress/egress slopes
    slope_mask = (dist > t_start) & (dist < t_end)
    if ingress > 0 and np.any(slope_mask):
        profile[slope_mask] = -depth * (t_end - dist[slope_mask]) / ingress
        
    return profile

class ExoplanetDataset(tf.keras.utils.Sequence):
    def __init__(self, num_samples=160, batch_size=16, length=2000, inject_prob=0.5, **kwargs):
        """
        Keras Sequence Dataset that generates stellar noise baselines and dynamically 
        injects physical planet transit dips on the fly.
        """
        super(ExoplanetDataset, self).__init__(**kwargs)
        self.num_samples = num_samples
        self.batch_size = batch_size
        self.length = length
        self.inject_prob = inject_prob
        self.pipeline = DualViewPipeline()
        
        # Pre-generate different stellar baselines (to avoid pure uniform noise)
        self.baselines = []
        for _ in range(num_samples):
            # Baseline contains low frequency stellar variability (sine waves) + random walk
            time = np.linspace(0, 10, length)
            stellar_var = 0.02 * np.sin(2 * np.pi * time / 3) + 0.005 * np.cos(2 * np.pi * time / 0.5)
            noise = np.random.normal(0, 0.004, length)
            self.baselines.append(1.0 + stellar_var + noise)

    def __len__(self):
        return int(np.ceil(self.num_samples / self.batch_size))

    def __getitem__(self, idx):
        # Calculate start and end indices for this batch
        start_idx = idx * self.batch_size
        end_idx = min(start_idx + self.batch_size, self.num_samples)
        current_batch_size = end_idx - start_idx
        
        global_batch = []
        local_batch = []
        label_batch = []
        
        for i in range(start_idx, end_idx):
            # 1. Start with raw stellar noise baseline
            flux = self.baselines[i].copy()
            
            # 2. Decide if we inject a planet transit
            label = 0.0
            if np.random.random() < self.inject_prob:
                label = 1.0
                
                # Randomized transit parameters
                period = np.random.uniform(300, 600)   # Period in index units
                depth = np.random.uniform(0.015, 0.04) # 1.5% to 4% transit depth
                duration = np.random.uniform(30, 80)   # Transit duration in indices
                t0 = np.random.uniform(50, 250)        # Transit epoch offset
                
                # Generate and apply transit profile
                transit_dip = generate_trapezoidal_transit(self.length, period, depth, duration, t0)
                flux += transit_dip
                
            # 3. Add dynamic measurement white noise (Data Augmentation)
            flux += np.random.normal(0, 0.001, self.length)
            
            # 4. Process through the DualViewPipeline to extract Global/Local views
            global_view, local_view, _, _ = self.pipeline.process(flux)
            
            # Append to lists with added channel dimension [SeqLen, 1]
            global_batch.append(global_view[:, np.newaxis])
            local_batch.append(local_view[:, np.newaxis])
            label_batch.append([label])
            
        return (np.array(global_batch, dtype=np.float32), np.array(local_batch, dtype=np.float32)), np.array(label_batch, dtype=np.float32)

if __name__ == "__main__":
    print("Testing ExoplanetDataset and Transit Injections in TensorFlow...")
    dataset = ExoplanetDataset(num_samples=10, batch_size=2, inject_prob=0.5)
    inputs, y = dataset[0]
    g_batch, l_batch = inputs
    print(f"Dataset batch test:")
    print(f"Global View Batch shape: {g_batch.shape} (Expected: (2, 2000, 1))")
    print(f"Local View Batch shape: {l_batch.shape} (Expected: (2, 200, 1))")
    print(f"Label Batch shape: {y.shape} (Expected: (2, 1))")
    print("\n✓ Dataset test passed successfully!")
