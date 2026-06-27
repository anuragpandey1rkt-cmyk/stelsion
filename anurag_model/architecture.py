import tensorflow as tf
from tensorflow.keras import layers, models

class DilatedResidualBlock1D(layers.Layer):
    def __init__(self, in_channels, out_channels, stride=1, dilation=1, dropout=0.2, **kwargs):
        """
        An upgraded 1D residual block using dilated convolutions to expand the 
        receptive field without losing sequence resolution.
        """
        super(DilatedResidualBlock1D, self).__init__(**kwargs)
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.stride = stride
        self.dilation = dilation
        self.dropout_rate = dropout

    def build(self, input_shape):
        actual_in_channels = input_shape[-1]
        
        # First convolution: standard kernel, handles downsampling if stride > 1
        self.conv1 = layers.Conv1D(
            self.out_channels, kernel_size=5, strides=self.stride, 
            padding='same', use_bias=False
        )
        self.bn1 = layers.BatchNormalization()
        self.relu1 = layers.ReLU()
        
        # Second convolution: Dilated convolution
        self.conv2 = layers.Conv1D(
            self.out_channels, kernel_size=5, strides=1, 
            dilation_rate=self.dilation, padding='same', use_bias=False
        )
        self.bn2 = layers.BatchNormalization()
        self.dropout = layers.Dropout(self.dropout_rate)
        self.relu2 = layers.ReLU()
        
        # Shortcut mapping if dimensions mismatch
        if self.stride != 1 or actual_in_channels != self.out_channels:
            self.shortcut_conv = layers.Conv1D(
                self.out_channels, kernel_size=1, strides=self.stride, 
                padding='same', use_bias=False
            )
            self.shortcut_bn = layers.BatchNormalization()
            
        super(DilatedResidualBlock1D, self).build(input_shape)

    def call(self, x, training=None):
        out = self.conv1(x)
        out = self.bn1(out, training=training)
        out = self.relu1(out)
        out = self.dropout(out, training=training)
        out = self.conv2(out)
        out = self.bn2(out, training=training)
        
        if hasattr(self, 'shortcut_conv'):
            shortcut_x = self.shortcut_conv(x)
            shortcut_x = self.shortcut_bn(shortcut_x, training=training)
        else:
            shortcut_x = x
            
        out += shortcut_x
        out = self.relu2(out)
        return out

class MultiHeadSelfAttention1D(layers.Layer):
    def __init__(self, in_channels, num_heads=4, **kwargs):
        """
        An upgraded Multi-Head Self-Attention layer for 1D temporal sequences.
        Splits channels into separate heads to capture multiple different periodicities
        and stellar patterns simultaneously.
        """
        super(MultiHeadSelfAttention1D, self).__init__(**kwargs)
        self.in_channels = in_channels
        self.num_heads = num_heads

    def build(self, input_shape):
        actual_in_channels = input_shape[-1]
        self.head_dim = actual_in_channels // self.num_heads
        
        assert self.head_dim * self.num_heads == actual_in_channels, "in_channels must be divisible by num_heads"
        
        # Query, Key, and Value projections using 1x1 convolutions
        self.q_proj = layers.Conv1D(actual_in_channels, kernel_size=1)
        self.k_proj = layers.Conv1D(actual_in_channels, kernel_size=1)
        self.v_proj = layers.Conv1D(actual_in_channels, kernel_size=1)
        
        # Final output mixing projection
        self.out_proj = layers.Conv1D(actual_in_channels, kernel_size=1)
        
        # Learnable gating parameter initialized to 0
        self.gamma = self.add_weight(
            name='gamma',
            shape=(1,),
            initializer='zeros',
            trainable=True
        )
        super(MultiHeadSelfAttention1D, self).build(input_shape)

    def call(self, x, training=None):
        # Input shape: [Batch, SeqLen, Channels]
        batch_size = tf.shape(x)[0]
        seq_len = tf.shape(x)[1]
        
        # 1. Project Query, Key, Value -> [B, L, C]
        q = self.q_proj(x)
        k = self.k_proj(x)
        v = self.v_proj(x)
        
        # 2. Reshape to multi-head shape: [B, L, H, D]
        q = tf.reshape(q, (batch_size, seq_len, self.num_heads, self.head_dim))
        k = tf.reshape(k, (batch_size, seq_len, self.num_heads, self.head_dim))
        v = tf.reshape(v, (batch_size, seq_len, self.num_heads, self.head_dim))
        
        # 3. Transpose for matrix multiplication:
        # q -> [B, H, L, D]
        # k -> [B, H, D, L]
        # v -> [B, H, L, D]
        q = tf.transpose(q, perm=[0, 2, 1, 3])
        k = tf.transpose(k, perm=[0, 2, 3, 1])
        v = tf.transpose(v, perm=[0, 2, 1, 3])
        
        # 4. Calculate Scaled Dot-Product Attention
        # energy shape: [B, H, L, L]
        energy = tf.matmul(q, k) / tf.math.sqrt(tf.cast(self.head_dim, tf.float32))
        attention = tf.nn.softmax(energy, axis=-1)
        
        # 5. Multiply attention weights with Value -> [B, H, L, D]
        out = tf.matmul(attention, v)
        
        # 6. Concatenate heads and project output
        # [B, H, L, D] -> transpose to [B, L, H, D] -> view as [B, L, C]
        out = tf.transpose(out, perm=[0, 2, 1, 3])
        out = tf.reshape(out, (batch_size, seq_len, self.in_channels))
        out = self.out_proj(out)
        
        # 7. Apply residual connection gated by gamma
        out = self.gamma * out + x
        
        # Average attention maps across heads for Grad-CAM/visualization -> [B, L, L]
        mean_attention = tf.reduce_mean(attention, axis=1)
        
        return out, mean_attention

class LocalFeatureExtractor1D(layers.Layer):
    def __init__(self, dropout=0.2, **kwargs):
        """
        Extracts high-resolution features from the zoomed-in local folded transit view.
        Since sequence length is small (200 points), a compact CNN layout is used.
        """
        super(LocalFeatureExtractor1D, self).__init__(**kwargs)
        self.dropout_rate = dropout

    def build(self, input_shape):
        self.conv1 = layers.Conv1D(32, kernel_size=5, strides=2, padding='same', use_bias=False)
        self.bn1 = layers.BatchNormalization()
        self.relu1 = layers.ReLU()
        self.drop1 = layers.Dropout(self.dropout_rate)
        
        self.conv2 = layers.Conv1D(64, kernel_size=5, strides=2, padding='same', use_bias=False)
        self.bn2 = layers.BatchNormalization()
        self.relu2 = layers.ReLU()
        self.drop2 = layers.Dropout(self.dropout_rate)
        
        self.conv3 = layers.Conv1D(128, kernel_size=5, strides=2, padding='same', use_bias=False)
        self.bn3 = layers.BatchNormalization()
        self.relu3 = layers.ReLU()
        self.drop3 = layers.Dropout(self.dropout_rate)
        
        self.gap = layers.GlobalAveragePooling1D()
        super(LocalFeatureExtractor1D, self).build(input_shape)

    def call(self, x, training=None):
        # x shape: [B, 200, 1]
        x = self.conv1(x)
        x = self.bn1(x, training=training)
        x = self.relu1(x)
        x = self.drop1(x, training=training)
        
        x = self.conv2(x)
        x = self.bn2(x, training=training)
        x = self.relu2(x)
        x = self.drop2(x, training=training)
        
        x = self.conv3(x)
        x = self.bn3(x, training=training)
        x = self.relu3(x)
        x = self.drop3(x, training=training)
        
        x = self.gap(x) # [B, 128]
        return x

class UpgradedExoplanetDetectorNet(models.Model):
    def __init__(self, input_len=2000, dropout=0.3, num_heads=4, **kwargs):
        """
        The SOTA Upgraded Exoplanet Classification Network (Phase 2 Multi-Input in TF).
        Integrates:
        - **Global View Branch (2000 pts)**: Processes the folded full orbit through
          Dilated Convolutions and Multi-Head Self-Attention.
        - **Local View Branch (200 pts)**: Processes the zoomed-in primary transit
          dip shape to check ingress/egress transit geometry.
        - **Feature Fusion**: Concatenates both representations for final classification.
        """
        super(UpgradedExoplanetDetectorNet, self).__init__(**kwargs)
        self.input_len = input_len
        self.dropout_rate = dropout
        self.num_heads = num_heads

        # --- GLOBAL BRANCH SETUP ---
        self.global_conv = layers.Conv1D(32, kernel_size=7, strides=2, padding='same', use_bias=False)
        self.global_bn = layers.BatchNormalization()
        self.global_relu = layers.ReLU()
        self.global_maxpool = layers.MaxPool1D(pool_size=3, strides=2, padding='same')
        
        self.global_res1 = DilatedResidualBlock1D(32, 64, stride=2, dilation=1, dropout=dropout)
        self.global_res2 = DilatedResidualBlock1D(64, 128, stride=2, dilation=2, dropout=dropout)
        self.global_res3 = DilatedResidualBlock1D(128, 256, stride=2, dilation=4, dropout=dropout)
        
        self.global_attention = MultiHeadSelfAttention1D(256, num_heads=num_heads)
        self.global_gap = layers.GlobalAveragePooling1D()
        
        # --- LOCAL BRANCH SETUP ---
        self.local_branch = LocalFeatureExtractor1D(dropout=dropout)
        
        # --- CLASSIFICATION HEAD ---
        # Combines Global (256 features) and Local (128 features) branches
        self.fc1 = layers.Dense(64, activation='relu')
        self.dropout_layer = layers.Dropout(dropout)
        self.fc2 = layers.Dense(1, activation='sigmoid')
        
    def compile(self, optimizer, loss_fn, **kwargs):
        super(UpgradedExoplanetDetectorNet, self).compile(**kwargs)
        self.optimizer = optimizer
        self.loss_fn = loss_fn
        self.loss_metric = tf.keras.metrics.Mean(name="loss")
        self.acc_metric = tf.keras.metrics.BinaryAccuracy(name="accuracy")

    @property
    def metrics(self):
        return [self.loss_metric, self.acc_metric]

    def train_step(self, data):
        x, y = data
        with tf.GradientTape() as tape:
            y_pred, _ = self(x, training=True)
            loss = self.loss_fn(y, y_pred)
            
        grads = tape.gradient(loss, self.trainable_variables)
        self.optimizer.apply_gradients(zip(grads, self.trainable_variables))
        
        self.loss_metric.update_state(loss)
        self.acc_metric.update_state(y, y_pred)
        return {"loss": self.loss_metric.result(), "accuracy": self.acc_metric.result()}

    def test_step(self, data):
        x, y = data
        y_pred, _ = self(x, training=False)
        loss = self.loss_fn(y, y_pred)
        
        self.loss_metric.update_state(loss)
        self.acc_metric.update_state(y, y_pred)
        return {"loss": self.loss_metric.result(), "accuracy": self.acc_metric.result()}

    def call(self, inputs, training=None):
        """
        Processes dual inputs: global_x [Batch, 2000, 1] and local_x [Batch, 200, 1].
        Accepts inputs either as a list/tuple of two tensors or a single dict.
        """
        if isinstance(inputs, dict):
            global_x = inputs['global']
            local_x = inputs['local']
        else:
            global_x, local_x = inputs
            
        # Ensure channel dimensions are present [Batch, SeqLen, 1]
        if len(global_x.shape) == 2:
            global_x = tf.expand_dims(global_x, axis=-1)
        if len(local_x.shape) == 2:
            local_x = tf.expand_dims(local_x, axis=-1)
            
        # 1. Global View Branch
        g = self.global_conv(global_x)
        g = self.global_bn(g, training=training)
        g = self.global_relu(g)
        g = self.global_maxpool(g)
        g = self.global_res1(g, training=training)
        g = self.global_res2(g, training=training)
        g = self.global_res3(g, training=training)
        g, attn_map = self.global_attention(g, training=training)
        global_feats = self.global_gap(g) # [Batch, 256]
        
        # 2. Local View Branch
        local_feats = self.local_branch(local_x, training=training) # [Batch, 128]
        
        # 3. Feature Fusion & Classification
        fused = tf.concat([global_feats, local_feats], axis=-1) # [Batch, 384]
        
        x = self.fc1(fused)
        x = self.dropout_layer(x, training=training)
        x = self.fc2(x)
        
        return x, attn_map
