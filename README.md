# Stelsion: AI-Enabled Detection of Exoplanets from Noisy Light Curves

A production-grade, end-to-end exoplanet detection platform for Kepler and TESS light curves. By integrating state-of-the-art 1D Convolutional Neural Networks (CNNs), Residual Blocks, and Multi-Head Self-Attention in PyTorch, AstroAI outperforms traditional BLS/TLS fitting methods while maintaining a computational cost significantly lower than ExoMiner.

## Key Features

- **Advanced Preprocessing Pipeline**: Handles missing data, applies Sigma Clipping, Wavelet Denoising, Savitzky-Golay smoothing, and removes stellar rotation variability.
- **Hybrid Deep Learning Model**:
  - **1D CNN**: Local feature extractors mapping individual transit dips.
  - **Residual Blocks**: Deep skip-connections to retain temporal features without vanishing gradients.
  - **Self-Attention**: Learns long-term global transit associations to check for periodicity, drastically reducing false positives.
- **Explainability Suite (XAI)**:
  - **1D Grad-CAM**: Activations identifying transit occurrences.
  - **Attention Weights**: Visualizing temporal correlations across light curves.
- **Scientific False-Positive Analysis**: Distinguishes true candidates from eclipsing binary systems, stellar spots/flares, and cosmic-ray instrument glitches.
- **NASA Inspired Dashboard**: Rich glassmorphic UI visualizing raw vs denoised curves, live neural network training plots, and explainability maps.

## Directory Structure

```
├── api/             # FastAPI routes & SQLite DB setup
├── preprocessing/   # Wavelet, SG, & outlier removal filters
├── models/          # PyTorch hybrid 1D CNN + Attention model architecture
├── training/        # Checkpointed PyTorch training & scheduling pipeline
├── evaluation/      # 1D Grad-CAM and false-positive heuristics
├── tests/           # Unit tests for models & signal processing
├── docker/          # Docker & Compose deployment configs
└── README.md
```

## Setup & Running Locally

### Backend API
1. Install Python packages:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the FastAPI server:
   ```bash
   uvicorn api.main:app --reload
   ```
3. Visit the Swagger documentation at `http://localhost:8000/docs`.

### Frontend Dashboard
1. Go to the `frontend/` directory:
   ```bash
   cd frontend
   ```
2. Install Node dependencies:
   ```bash
   npm install
   ```
3. Start the dev server:
   ```bash
   npm run dev
   ```
4. Access the dashboard at `http://localhost:3000`.

## Docker Compose Deployment

Run both backend and frontend instantly with Docker:
```bash
docker-compose -f docker/docker-compose.yml up --build
```
The dashboard will be served at `http://localhost:3000` with the API proxy running on `http://localhost:8000`.
