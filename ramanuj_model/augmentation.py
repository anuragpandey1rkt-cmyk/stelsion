import numpy as np

def generate_augmentations(time, flux, count=1):
    """
    Generates a list of physically realistic raw light curve augmentations:
    - Random temporal shift (rolling)
    - Gaussian noise injection (proportional to standard deviation)
    - Slight amplitude scaling (simulating transit depth changes)
    """
    augmentations = []
    
    # Always include the original, un-augmented curve
    augmentations.append((time.copy(), flux.copy()))
    
    for _ in range(count):
        aug_time = time.copy()
        aug_flux = flux.copy()
        
        # 1. Random temporal shift (rolling the array slightly)
        shift_range = max(5, int(len(flux) * 0.05))
        shift = np.random.randint(-shift_range, shift_range)
        aug_flux = np.roll(aug_flux, shift)
        
        # 2. Gaussian noise injection (5% of standard deviation)
        std_val = np.std(flux)
        if std_val > 1e-6:
            noise = np.random.normal(0, 0.05 * std_val, len(flux))
            aug_flux = aug_flux + noise
            
        # 3. Slight amplitude scaling (between 0.85 and 1.15)
        scale_factor = np.random.uniform(0.85, 1.15)
        aug_flux = aug_flux * scale_factor
        
        augmentations.append((aug_time, aug_flux))
        
    return augmentations
