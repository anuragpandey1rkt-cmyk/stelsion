import numpy as np
import scipy.signal as signal

class DualViewPipeline:
    def __init__(self, global_len=2000, local_len=200):
        self.global_len = global_len
        self.local_len = local_len

    def estimate_period_and_epoch(self, flux):
        """
        Estimates the transit period (P) and epoch (T0) from the flux array.
        Uses a median-filtered curve to find recurring dips.
        """
        flux = np.array(flux)
        n = len(flux)
        
        # Smooth curve to remove high-frequency noise
        smoothed = signal.medfilt(flux, 15)
        median_val = np.median(smoothed)
        
        # Locate the primary epoch (deepest dip)
        t0 = int(np.argmin(smoothed))
        
        # Find all dips below a threshold (median - 1.5% depth)
        threshold = median_val - 0.015
        dips = []
        for i in range(10, n - 10):
            if smoothed[i] == np.min(smoothed[i-10:i+10]) and smoothed[i] < threshold:
                dips.append(i)
                
        # Filter out close detections
        filtered_dips = []
        for d in dips:
            if not filtered_dips or (d - filtered_dips[-1]) > 30:
                filtered_dips.append(d)
                
        # Estimate period based on differences
        if len(filtered_dips) >= 2:
            diffs = np.diff(filtered_dips)
            period = float(np.mean(diffs))
        else:
            period = float(n / 2) # Default period fallback (half of sequence length)
            
        return period, t0

    def fold_light_curve(self, flux, period, t0):
        """
        Folds the light curve around the calculated period and epoch (t0).
        Resamples the folded curve to exactly global_len (2000) points.
        """
        n = len(flux)
        time = np.arange(n)
        
        # Calculate phase values normalized from [-0.5, 0.5]
        phases = ((time - t0) / period) % 1.0
        phases = np.where(phases > 0.5, phases - 1.0, phases)
        
        # Sort flux by phase
        sort_idx = np.argsort(phases)
        sorted_phases = phases[sort_idx]
        sorted_flux = flux[sort_idx]
        
        # Interpolate onto a uniform phase grid of size global_len (2000 points)
        uniform_phases = np.linspace(-0.5, 0.5, self.global_len)
        global_view = np.interp(uniform_phases, sorted_phases, sorted_flux)
        
        return global_view

    def extract_local_view(self, folded_flux):
        """
        Extracts the local view centered on phase 0.
        Since folded_flux phase grid is [-0.5, 0.5], phase 0 is exactly in the middle.
        For a 2000-point folded flux, we extract 200 points from index 900 to 1100.
        """
        mid_idx = len(folded_flux) // 2
        half_width = self.local_len // 2
        
        start_idx = mid_idx - half_width
        end_idx = mid_idx + half_width
        
        local_view = folded_flux[start_idx:end_idx]
        return local_view

    def process(self, raw_flux):
        """
        Runs the full dual-view pipeline on a raw light curve:
        Denoises it -> Finds period/epoch -> Folds (Global View) -> Zooms (Local View).
        """
        raw_flux = np.array(raw_flux)
        
        # 1. Basic Cleaning
        # Interpolate NaNs
        nans = np.isnan(raw_flux)
        if np.any(nans):
            x = np.arange(len(raw_flux))
            raw_flux[nans] = np.interp(x[nans], x[~nans], raw_flux[~nans])
            
        # Median normalization (relative centered at 0.0)
        median_val = np.median(raw_flux)
        if median_val != 0:
            raw_flux = (raw_flux / median_val) - 1.0
            
        # 2. Estimate Period & Epoch
        period, t0 = self.estimate_period_and_epoch(raw_flux)
        
        # 3. Fold for Global View
        global_view = self.fold_light_curve(raw_flux, period, t0)
        
        # 4. Extract Local View
        local_view = self.extract_local_view(global_view)
        
        return global_view, local_view, period, t0
