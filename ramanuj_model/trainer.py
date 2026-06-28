import os
import sys
import time
import json
import numpy as np
import tensorflow as tf
from sklearn.model_selection import StratifiedKFold
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import f1_score

# Prioritize workspace root and remove local dir to prevent module shadowing
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir in sys.path:
    sys.path.remove(script_dir)
if workspace_root in sys.path:
    sys.path.remove(workspace_root)
sys.path.insert(0, workspace_root)

from ramanuj_model.model import get_model
from ramanuj_model.dataset import prepare_datasets
from ramanuj_model.losses import get_loss
from ramanuj_model.callbacks import get_callbacks
from ramanuj_model.experiment import create_experiment_dir, save_experiment_results
from ramanuj_model.utils import get_system_metadata, set_seed, setup_gpu
from evaluation.metrics import calculate_metrics
import ramanuj_model.config as config

def optimize_threshold(y_true, y_prob):
    """
    Searches thresholds between 0.20 and 0.80 on validation set predictions
    to find the one that maximizes the F1 score.
    """
    best_thresh = 0.5
    best_f1 = -1.0
    for thresh in np.arange(0.20, 0.81, 0.01):
        y_pred = (y_prob >= thresh).astype(int)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = thresh
    return float(best_thresh), float(best_f1)

def train_model(config_overrides: dict = None):
    """
    Main training interface with Stratified Cross-Validation support.
    """
    set_seed(config.SEED)
    setup_gpu()
    
    # 1. Load train/val/test splits (Phase 1)
    (x_train, y_train), (x_val, y_val), (x_test, y_test) = prepare_datasets()
    
    # Configuration adjustments
    lr = config.LEARNING_RATE
    if config_overrides and "learning_rate" in config_overrides:
        lr = config_overrides["learning_rate"]
        
    optimizer_name = config.OPTIMIZER
    if config_overrides and "optimizer" in config_overrides:
        optimizer_name = config_overrides["optimizer"]
        
    loss_name = config.LOSS
    if config_overrides and "loss" in config_overrides:
        loss_name = config_overrides["loss"]
        
    epochs = config.EPOCHS
    if config_overrides and "epochs" in config_overrides:
        epochs = config_overrides["epochs"]
        
    batch_size = config.BATCH_SIZE
    if config_overrides and "batch_size" in config_overrides:
        batch_size = config_overrides["batch_size"]
        
    enable_kfold = config.ENABLE_KFOLD
    if config_overrides and "enable_kfold" in config_overrides:
        enable_kfold = config_overrides["enable_kfold"]
        
    start_time = time.time()
    
    # Prepare directories
    exp_dir = create_experiment_dir()
    os.makedirs(config.SAVED_MODELS_DIR, exist_ok=True)
    
    # Define optimizer compiler
    def compile_model(model):
        if optimizer_name == "adam":
            opt = tf.keras.optimizers.Adam(learning_rate=lr)
        elif optimizer_name == "sgd":
            opt = tf.keras.optimizers.SGD(learning_rate=lr, momentum=0.9)
        else:
            opt = tf.keras.optimizers.RMSprop(learning_rate=lr)
        loss_fn = get_loss(loss_name)
        model.compile(optimizer=opt, loss=loss_fn, metrics=['accuracy'])
        return opt
        
    best_threshold = 0.5
    best_f1_val = -1.0
    
    if enable_kfold:
        print("\n" + "=" * 50)
        print(f"RUNNING STRATIFIED {config.NUM_FOLDS}-FOLD CROSS VALIDATION")
        print("=" * 50)
        
        # Concatenate train and validation sets for CV
        x_all = np.concatenate([x_train, x_val], axis=0)
        y_all = np.concatenate([y_train, y_val], axis=0)
        
        skf = StratifiedKFold(n_splits=config.NUM_FOLDS, shuffle=True, random_state=config.SEED)
        
        fold_metrics = []
        best_fold_model = None
        best_fold_idx = -1
        best_fold_val_data = None
        best_fold_history = None
        
        for fold_idx, (train_idx, val_idx) in enumerate(skf.split(x_all, y_all)):
            print(f"\n--- Training Fold {fold_idx + 1}/{config.NUM_FOLDS} ---")
            x_tr_fold, y_tr_fold = x_all[train_idx], y_all[train_idx]
            x_val_fold, y_val_fold = x_all[val_idx], y_all[val_idx]
            
            # Compute class weights dynamically
            class_weights_arr = compute_class_weight('balanced', classes=np.unique(y_tr_fold), y=y_tr_fold)
            class_weights = dict(zip(np.unique(y_tr_fold), class_weights_arr))
            
            fold_model = get_model(**(config_overrides or {}))
            opt = compile_model(fold_model)
            
            fold_callbacks = get_callbacks(
                experiment_dir=os.path.join(exp_dir, f"fold_{fold_idx+1}"),
                val_data=(x_val_fold, y_val_fold),
                patience_early_stopping=15,
                patience_reduce_lr=5
            )
            
            fold_history = fold_model.fit(
                x_tr_fold, y_tr_fold,
                validation_data=(x_val_fold, y_val_fold),
                epochs=epochs,
                batch_size=batch_size,
                callbacks=fold_callbacks,
                class_weight=class_weights,
                verbose=1
            )
            
            # Load best epoch weights (saved by F1CheckpointCallback)
            best_weights_path = os.path.join(exp_dir, f"fold_{fold_idx+1}", "model_best.weights.h5")
            if os.path.exists(best_weights_path):
                fold_model.load_weights(best_weights_path)
                
            y_val_prob = fold_model.predict(x_val_fold).flatten()
            thresh_opt, f1_opt = optimize_threshold(y_val_fold, y_val_prob)
            y_val_pred = (y_val_prob >= thresh_opt).astype(int)
            
            metrics = calculate_metrics(y_val_fold, y_val_pred, y_val_prob)
            metrics["optimal_threshold"] = thresh_opt
            fold_metrics.append(metrics)
            
            print(f"Fold {fold_idx+1} Val F1 Score (Threshold={thresh_opt:.2f}): {metrics['f1_score']:.4f}")
            
            if metrics["f1_score"] > best_f1_val:
                best_f1_val = metrics["f1_score"]
                best_fold_idx = fold_idx
                best_fold_model = fold_model
                best_fold_val_data = (x_val_fold, y_val_fold, y_val_prob)
                best_fold_history = fold_history
                best_threshold = thresh_opt
                
        # Calculate CV averages
        accs = [m["accuracy"] for m in fold_metrics]
        precs = [m["precision"] for m in fold_metrics]
        recs = [m["recall"] for m in fold_metrics]
        f1s = [m["f1_score"] for m in fold_metrics]
        
        print("\n" + "=" * 50)
        print("CROSS VALIDATION RESULTS SUMMARY")
        print("=" * 50)
        print(f"Mean Accuracy:  {np.mean(accs):.4f} ± {np.std(accs):.4f}")
        print(f"Mean Precision: {np.mean(precs):.4f} ± {np.std(precs):.4f}")
        print(f"Mean Recall:    {np.mean(recs):.4f} ± {np.std(recs):.4f}")
        print(f"Mean F1 Score:  {np.mean(f1s):.4f} ± {np.std(f1s):.4f}")
        print(f"Best Fold:      Fold {best_fold_idx + 1}")
        print("=" * 50)
        
        model = best_fold_model
        x_val_final, y_val_final, y_val_prob_final = best_fold_val_data
        history = best_fold_history
        val_metrics = fold_metrics[best_fold_idx]
        
    else:
        # Standard Single Fold Training
        print("\nRunning standard single split training...")
        class_weights_arr = compute_class_weight('balanced', classes=np.unique(y_train), y=y_train)
        class_weights = dict(zip(np.unique(y_train), class_weights_arr))
        
        model = get_model(**(config_overrides or {}))
        opt = compile_model(model)
        
        callbacks = get_callbacks(
            experiment_dir=exp_dir,
            val_data=(x_val, y_val),
            patience_early_stopping=15,
            patience_reduce_lr=5
        )
        
        history = model.fit(
            x_train, y_train,
            validation_data=(x_val, y_val),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=callbacks,
            class_weight=class_weights,
            verbose=1
        )
        
        best_weights_path = os.path.join(exp_dir, "model_best.weights.h5")
        if os.path.exists(best_weights_path):
            model.load_weights(best_weights_path)
            
        x_val_final, y_val_final = x_val, y_val
        y_val_prob_final = model.predict(x_val).flatten()
        best_threshold, best_f1_val = optimize_threshold(y_val_final, y_val_prob_final)
        y_val_pred = (y_val_prob_final >= best_threshold).astype(int)
        val_metrics = calculate_metrics(y_val_final, y_val_pred, y_val_prob_final)
        
    elapsed_time = time.time() - start_time
    
    # Save the consolidated experiment metadata & reports
    save_experiment_results(
        exp_dir=exp_dir,
        model=model,
        history=history,
        val_metrics=val_metrics,
        config_overrides=config_overrides,
        y_val_true=y_val_final,
        y_val_prob=y_val_prob_final,
        threshold=best_threshold,
        best_epoch=getattr(history, 'params', {}).get('epochs', 1),
        elapsed_time=elapsed_time,
        train_size=len(x_train),
        val_size=len(x_val_final),
        pos_size=int(np.sum(y_train == 1.0) + np.sum(y_val_final == 1.0)),
        neg_size=int(np.sum(y_train == 0.0) + np.sum(y_val_final == 0.0))
    )
    
    # Save optimized threshold and model metrics in model_meta.json
    meta_path = os.path.join(config.SAVED_MODELS_DIR, "model_meta.json")
    with open(meta_path, "w") as f:
        json.dump({
            "threshold": best_threshold,
            "val_f1_score": best_f1_val,
            "architecture": config.ARCHITECTURE,
            "loss": config.LOSS
        }, f, indent=4)
    print(f"Optimal threshold saved to: {meta_path}")
    
    # Recompile with standard binary_crossentropy to ensure it loads without custom loss functions
    model.compile(optimizer=opt, loss='binary_crossentropy', metrics=['accuracy'])
    
    # Save final model checkouts (.keras and .h5 formats for absolute compatibility)
    final_keras_path = os.path.join(config.SAVED_MODELS_DIR, f"{config.ARCHITECTURE}_model.keras")
    final_h5_path = os.path.join(config.SAVED_MODELS_DIR, f"{config.ARCHITECTURE}_model.h5")
    
    model.save(final_keras_path)
    model.save(final_h5_path)
    print(f"Saved primary native model to: {final_keras_path}")
    print(f"Saved secondary H5 model to: {final_h5_path}")
    
    return final_keras_path, val_metrics

def run_optuna_study():
    """
    Optimizes validation F1 score across several trials.
    """
    (x_train, y_train), (x_val, y_val), _ = prepare_datasets()
    if x_val is None:
        raise ValueError("Optuna study requires a validation dataset.")
        
    def objective(trial):
        lr = trial.suggest_float("learning_rate", 1e-4, 1e-2, log=True)
        dropout = trial.suggest_float("dropout_rate", 0.1, 0.5)
        batch_size = trial.suggest_categorical("batch_size", [4, 8, 16])
        optimizer_name = trial.suggest_categorical("optimizer", ["adam", "sgd"])
        
        model = get_model(dropout_rate=dropout)
        
        if optimizer_name == "adam":
            opt = tf.keras.optimizers.Adam(learning_rate=lr)
        else:
            opt = tf.keras.optimizers.SGD(learning_rate=lr, momentum=0.9)
            
        model.compile(optimizer=opt, loss=get_loss(config.LOSS), metrics=['accuracy'])
        
        es = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=3, restore_best_weights=True)
        model.fit(
            x_train, y_train,
            validation_data=(x_val, y_val),
            epochs=5,
            batch_size=batch_size,
            callbacks=[es],
            verbose=0
        )
        
        y_val_prob = model.predict(x_val).flatten()
        y_val_pred = (y_val_prob >= 0.5).astype(int)
        metrics = calculate_metrics(y_val, y_val_pred, y_val_prob)
        return metrics["f1_score"]
        
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=config.OPTUNA_TRIALS)
    
    print("\n" + "=" * 50)
    print("OPTUNA OPTIMIZATION STUDY RESULTS")
    print("=" * 50)
    print(f"Best validation F1 Score: {study.best_trial.value:.4f}")
    print("Best parameters:")
    for k, v in study.best_trial.params.items():
        print(f"  - {k}: {v}")
    print("=" * 50)
    
    return study.best_trial.params
