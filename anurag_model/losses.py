import tensorflow as tf

class BinaryFocalLoss(tf.keras.losses.Loss):
    def __init__(self, alpha=0.25, gamma=2.0, name="binary_focal_loss", **kwargs):
        """
        Binary Focal Loss for highly imbalanced exoplanet classification in TensorFlow.
        FL(pt) = -alpha * (1 - pt)^gamma * log(pt)
        """
        super(BinaryFocalLoss, self).__init__(name=name, **kwargs)
        self.alpha = alpha
        self.gamma = gamma

    def call(self, y_true, y_pred):
        # Convert inputs to float32
        y_true = tf.cast(y_true, tf.float32)
        y_pred = tf.cast(y_pred, tf.float32)
        
        # Avoid log(0) and clamp probabilities
        eps = 1e-7
        y_pred = tf.clip_by_value(y_pred, eps, 1.0 - eps)
        
        # Standard Binary Cross Entropy
        bce = - (y_true * tf.math.log(y_pred) + (1.0 - y_true) * tf.math.log(1.0 - y_pred))
        
        # pt represents model's probability of the correct class
        pt = y_true * y_pred + (1.0 - y_true) * (1.0 - y_pred)
        
        # Calculate focal weights: downweights easy examples where pt is close to 1
        focal_weight = tf.pow(1.0 - pt, self.gamma)
        
        # Class balance factor
        alpha_t = y_true * self.alpha + (1.0 - y_true) * (1.0 - self.alpha)
        
        # Fused loss
        loss = alpha_t * focal_weight * bce
        
        return tf.reduce_mean(loss)
