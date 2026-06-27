import os
import sys
import argparse
import tensorflow as tf

# Ensure parent directory is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anurag_model.architecture import UpgradedExoplanetDetectorNet
from anurag_model.losses import BinaryFocalLoss
from anurag_model.dataset import ExoplanetDataset

def train_model(epochs=5, batch_size=16, lr=0.001):
    print("--- Initializing Phase 3 TensorFlow Training Pipeline ---")
    
    # 1. Instantiate datasets and dataloaders
    print("Generating training and validation datasets...")
    train_dataset = ExoplanetDataset(num_samples=160, batch_size=batch_size, inject_prob=0.5)
    val_dataset = ExoplanetDataset(num_samples=48, batch_size=batch_size, inject_prob=0.5)
    
    # 2. Instantiate model, loss, and optimizer
    model = UpgradedExoplanetDetectorNet(input_len=2000, dropout=0.3, num_heads=4)
    optimizer = tf.keras.optimizers.Adam(learning_rate=lr)
    criterion = BinaryFocalLoss(alpha=0.25, gamma=2.0)
    
    # Compile the model using Keras compile
    model.compile(optimizer=optimizer, loss_fn=criterion)
    
    print(f"Training Configuration:")
    print(f"  Epochs: {epochs}")
    print(f"  Batch Size: {batch_size}")
    print(f"  Learning Rate: {lr}")
    print(f"  Loss Function: Focal Loss (alpha=0.25, gamma=2.0)")
    
    # 3. Fit Model using standard Keras .fit()
    history = model.fit(
        train_dataset,
        validation_data=val_dataset,
        epochs=epochs,
        verbose=1
    )
    
    # 4. Save model weights
    os.makedirs("saved_models", exist_ok=True)
    checkpoint_path = os.path.join("saved_models", "best_tensorflow_model.weights.h5")
    model.save_weights(checkpoint_path)
    print(f"\n✓ Training Completed! Saved best model weights to: {checkpoint_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AstroAI TensorFlow Training Script")
    parser.add_argument("--epochs", type=int, default=5, help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=16, help="Batch size")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate")
    args = parser.parse_args()
    
    train_model(epochs=args.epochs, batch_size=args.batch_size, lr=args.lr)
