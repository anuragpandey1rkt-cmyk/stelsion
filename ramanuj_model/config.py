import os

# Base directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVED_MODELS_DIR = os.path.join(BASE_DIR, "saved_models")
EXPERIMENTS_DIR = os.path.join(BASE_DIR, "experiments")

# General settings
SEED = 42
TF_GPU_MEMORY_GROWTH = True

# Preprocessing Stage Toggles (Phase 2)
STAGE_NAN_INTERP = True
STAGE_SIGMA_CLIP = True
STAGE_NOISE_EST = True
STAGE_ADAPTIVE_FILTER = True
STAGE_DETRENDING = True
STAGE_NORMALIZATION = True
PREPROCESSING = "adaptive_v2"

# Shape configurations (Phase 4)
GLOBAL_VIEW_LEN = 2000
LOCAL_VIEW_LEN = 200
ORBIT_MATRIX_SHAPE = (9, 800)  # Orbits x Bins
INPUT_SHAPE = (9, 800, 1)
SEGMENT_LENGTH = 7200         # Matches final benchmark input (9 * 800)

# BLS Parameters (Phase 3)
BLS_MIN_PERIOD = 0.5   # in days
BLS_MAX_PERIOD = 20.0  # in days
BLS_OVERSAMPLE = 5

# MC Dropout Settings (Phase 7)
MC_DROPOUT_RUNS = 20

# Model training settings (Phase 9)
BATCH_SIZE = 8
EPOCHS = 80
LEARNING_RATE = 0.0003
OPTIMIZER = "adam"       # "adam", "sgd"
LOSS = "focal"           # "bce", "focal"
WEIGHT_DECAY = 1e-4
DROPOUT_RATE = 0.4       # Slightly increased from 0.3 for better regularization

# Active architecture selection
# Options: "baseline", "inceptiontime", "minor_axis_attention", "hybrid"
ARCHITECTURE = "hybrid"

# Cross-Validation Settings
ENABLE_KFOLD = True
NUM_FOLDS = 5

# Data Augmentation settings
ENABLE_TRAIN_AUGMENTATION = True

# Hyperparameter optimization (Optuna)
OPTUNA_TRIALS = 10
