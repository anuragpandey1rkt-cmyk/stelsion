import tensorflow as tf

def focal_loss(gamma=2.0, alpha=0.25):
    """
    Computes Focal Loss for binary classification tasks.
    Helps down-weight easy examples and focus training on hard negatives.
    """
    def loss(y_true, y_pred):
        y_true = tf.cast(y_true, tf.float32)
        # Prevent log(0) or log(1) issues
        epsilon = tf.keras.backend.epsilon()
        y_pred = tf.clip_by_value(y_pred, epsilon, 1.0 - epsilon)
        
        bce = -y_true * tf.math.log(y_pred) - (1.0 - y_true) * tf.math.log(1.0 - y_pred)
        
        # Calculate modulation weights
        weights = y_true * alpha * tf.math.pow(1.0 - y_pred, gamma) + \
                  (1.0 - y_true) * (1.0 - alpha) * tf.math.pow(y_pred, gamma)
                  
        return tf.reduce_mean(bce * weights)
    return loss

def get_loss(loss_name="bce", **kwargs):
    if loss_name in ["focal", "focal_loss"]:
        g = kwargs.get("gamma", 2.0)
        a = kwargs.get("alpha", 0.25)
        return focal_loss(gamma=g, alpha=a)
    return tf.keras.losses.BinaryCrossentropy()
