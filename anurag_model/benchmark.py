import sys
import os
import time
import tensorflow as tf
import numpy as np

# Ensure parent directory is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anurag_model.architecture import UpgradedExoplanetDetectorNet

def benchmark_model():
    print("--- Phase 2 TensorFlow Dual-Input Model Benchmark ---")
    
    # 1. Initialize model
    model = UpgradedExoplanetDetectorNet(input_len=2000, dropout=0.3, num_heads=4)
    
    # Generate dummy global & local inputs (size 1 for single-sample latency)
    dummy_global = tf.random.normal((1, 2000, 1))
    dummy_local = tf.random.normal((1, 200, 1))
    
    # Warmup and build layers
    print("Building model layers...")
    for _ in range(50):
        _ = model([dummy_global, dummy_local], training=False)
        
    # 2. Calculate trainable parameters
    total_params = model.count_params()
    print(f"Total Trainable Parameters: {total_params:,}")
    
    # 3. Measure inference latency
    num_runs = 500
    print(f"Running latency benchmark over {num_runs} iterations...")
    start_time = time.perf_counter()
    for _ in range(num_runs):
        _ = model([dummy_global, dummy_local], training=False)
    end_time = time.perf_counter()
    
    avg_latency_ms = ((end_time - start_time) / num_runs) * 1000
    print(f"Average Inference Latency: {avg_latency_ms:.3f} ms")
    
if __name__ == "__main__":
    benchmark_model()
