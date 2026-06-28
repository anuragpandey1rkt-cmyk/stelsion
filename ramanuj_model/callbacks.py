import os
import numpy as np
import tensorflow as tf
from sklearn.metrics import precision_recall_fscore_support

class F1CheckpointCallback(tf.keras.callbacks.Callback):
    """
    Custom Keras callback to calculate validation Precision, Recall, and F1 at epoch end.
    Implements checkpointing based on validation F1 score.
    """
    def __init__(self, val_data, checkpoint_path):
        super().__init__()
        self.x_val, self.y_val = val_data
        self.checkpoint_path = checkpoint_path
        self.best_f1 = -1.0
        self.best_weights = None
        self.best_epoch = 0
        
    def on_epoch_end(self, epoch, logs=None):
        logs = logs or {}
        
        # Predict on validation data
        y_val_prob = self.model.predict(self.x_val, verbose=0).flatten()
        y_val_pred = (y_val_prob >= 0.5).astype(int)
        
        # Calculate metrics
        prec, rec, f1, _ = precision_recall_fscore_support(
            self.y_val, y_val_pred, average='binary', zero_division=0
        )
        
        # Inject into logs dictionary for TensorBoard / CSVLogger
        logs['val_precision'] = float(prec)
        logs['val_recall'] = float(rec)
        logs['val_f1'] = float(f1)
        
        print(f"\n - Epoch {epoch+1:02d}: Val Precision: {prec:.4f} | Val Recall: {rec:.4f} | Val F1: {f1:.4f}")
        
        if f1 > self.best_f1:
            self.best_f1 = f1
            self.best_epoch = epoch + 1
            self.best_weights = self.model.get_weights()
            # Save best weights
            self.model.save_weights(self.checkpoint_path)
            print(f"   * New Best Validation F1: {f1:.4f} (Saved weights)")
        else:
            print(f"   Validation F1 did not improve.")

def get_callbacks(experiment_dir, val_data, patience_early_stopping=15, patience_reduce_lr=5):
    """
    Creates and returns Keras callbacks:
    - F1CheckpointCallback: monitors Validation F1, checkpoints best model.
    - EarlyStopping: prevents overfitting on validation loss.
    - ReduceLROnPlateau: decreases learning rate dynamically when val_loss plateaus.
    - TensorBoard: logs training metrics.
    """
    os.makedirs(experiment_dir, exist_ok=True)
    checkpoint_path = os.path.join(experiment_dir, "model_best.weights.h5")
    log_dir = os.path.join(experiment_dir, "logs")
    
    callbacks = [
        F1CheckpointCallback(
            val_data=val_data,
            checkpoint_path=checkpoint_path
        ),
        tf.keras.callbacks.EarlyStopping(
            monitor='val_loss',
            patience=patience_early_stopping,
            restore_best_weights=True,
            verbose=1
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=patience_reduce_lr,
            min_lr=1e-6,
            verbose=1
        ),
        tf.keras.callbacks.TensorBoard(
            log_dir=log_dir,
            histogram_freq=0
        )
    ]
    
    return callbacks
