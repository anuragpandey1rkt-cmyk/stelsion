# Dataset Fetcher (Resume Supported)
# Safe to run multiple times. Already downloaded files will be skipped.

import os
import time
import numpy as np
import pandas as pd
# pyrefly: ignore [missing-import]
from lightkurve import search_lightcurve

# -----------------------------
# Load labeled dataset
# -----------------------------
koi = pd.read_csv(
    "modified datasets/koi_cumulative_labeled.csv",
    comment="#"
)

# Download up to 250 samples per class
subset = (
    koi.groupby("signal_class", group_keys=False)
       .head(250)
)

# Output folder
os.makedirs("dataset", exist_ok=True)

# Load existing index if present
if os.path.exists("dataset_index.csv"):
    records = pd.read_csv("dataset_index.csv").to_dict("records")
else:
    records = []

downloaded = {
    r["kepid"] for r in records
}

print(f"Already downloaded: {len(downloaded)}")

# -----------------------------
# Download loop
# -----------------------------
for _, row in subset.iterrows():

    kepid = int(row["kepid"])
    label = row["signal_class"]

    filename = f"dataset/{kepid}.npz"

    # Skip existing downloads
    if kepid in downloaded or os.path.exists(filename):
        print(f"Skipping {kepid}")
        continue

    try:
        print(f"Downloading {kepid}...")

        lc = search_lightcurve(
            f"KIC {kepid}",
            mission="Kepler"
        ).download()

        if lc is None:
            print(f"No lightcurve found for {kepid}")
            continue

        lc = lc.remove_nans()
        lc = lc.normalize()

        np.savez(
            filename,
            time=lc.time.value,
            flux=lc.flux.value
        )

        records.append({
            "kepid": kepid,
            "label": label,
            "file": filename
        })

        pd.DataFrame(records).to_csv(
            "dataset_index.csv",
            index=False
        )

        print(f"✓ Downloaded {kepid}")

        # Small delay to avoid hammering MAST
        time.sleep(0.5)

    except Exception as e:
        print(f"✗ Failed {kepid}: {e}")
        continue

print("\n===================================")
print(f"Total downloaded: {len(records)}")
print("Dataset download complete.")
print("===================================")