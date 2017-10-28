import tensorflow as tf
import numpy as np
from utils import Utils as utils

allowed_activations = ['sigmoid', 'tanh', 'softmax', 'relu', 'linear', 'softplus']
allowed_noises = ['none', 'gaussian', 'mask']
allowed_losses = ['rmse', 'cross-entropy']

class StackedAutoEncoder:
    """A deep autoencoder with denoising capability"""

    def assertions(self):
        global allowed_activations, allowed_noises, allowed_losses
        assert 'list' in str(
            type(self.dims)), 'dims must be a list even if there is one layer.'
        assert len(self.epoch) == len(
            self.dims), "No. of epochs must equal to no. of hidden layers"
        assert len(self.activations) == len(
            self.dims), "No. of activations must equal to no. of hidden layers"
        assert len(self.decoding_activations) == len(
            self.dims), "No. of decoding activations must equal to no. of hidden layers"
        assert len(self.loss) == len(
            self.dims), "No. of loss functions must equal to no. of hidden layers"
        assert all(
            True if x > 0 else False
            for x in self.epoch), "No. of epoch must be atleast 1"
        assert set(self.activations + allowed_activations) == set(
            allowed_activations), "Incorrect activation given."
        assert set(self.loss + allowed_losses) == set(
            allowed_losses), "Incorrect loss given."
        assert utils.noise_validator(
            self.noise, allowed_noises), "Incorrect noises given"

    def __init__(self, dims, activations, decoding_activations, loss, noise, epoch=1000,
                 lr=0.001, batch_size=100, print_step=50):
        self.print_step = print_step
        self.batch_size = batch_size
        self.lr = lr
        self.loss = loss
        self.activations = activations
        self.decoding_activations = decoding_activations
        self.noise = noise
        self.epoch = epoch
        self.dims = dims
        self.assertions()
        self.depth = len(dims)
        self.weights, self.biases, self.decoding_biases = [], [], []

    def add_noise(self, x, layer):
        if self.noise[layer] == 'none':
            return x
        if self.noise[layer] == 'gaussian':
            n = np.random.normal(0, 0.1, (len(x), len(x[0])))
            return x + n
        if 'mask' in self.noise[layer]:
            frac = float(self.noise[layer].split('-')[1])
            temp = np.copy(x)
            for i in temp:
                n = np.random.choice(len(i), int(round(frac * len(i))), replace=False)
                i[n] = 0
            return temp
        if self.noise[layer] == 'sp':
            pass

    def fit(self, x):
        for i in range(self.depth):
            print('Layer {0}'.format(i + 1))
            tmp = np.copy(x)
            tmp = self.add_noise(tmp, i)

            x = self.run(data_x=tmp,
                         activation=self.activations[i],
                         decoding_activation=self.decoding_activations[i],
                         data_x_=x,
                         hidden_dim=self.dims[i],
                         epoch=self.epoch[i],
                         loss=self.loss[i],
                         batch_size=self.batch_size,
                         lr=self.lr,
                         print_step=self.print_step)

    def finetune(self, data_x):
        print('Fine Tuning')
        tf.reset_default_graph()
        input_dim = len(data_x[0])
        sess = tf.Session()
        masked_data_x = np.copy(data_x)
        masked_data_x = self.add_noise(masked_data_x, 0)

        x = tf.placeholder(dtype=tf.float32, shape=[None, input_dim], name='x')
        x_ = tf.placeholder(dtype=tf.float32, shape=[None, input_dim], name='x_')

        weights, biases, decoding_biases = [],[],[]
        for w, b, b_ in zip(self.weights, self.biases, self.decoding_biases):
            weights.append(tf.Variable(np.array(w), dtype=tf.float32))
            biases.append(tf.Variable(np.array(b), dtype=tf.float32))
            decoding_biases.append(tf.Variable(np.array(b_), dtype=tf.float32))

        status = x
        #Encoding
        for i in range(self.depth):
            status = self.activate(tf.matmul(status, weights[i]) + biases[i], self.activations[i])
        #Decoding
        for i in range(self.depth-1, -1, -1):
            status = self.activate(tf.matmul(status, tf.transpose(weights[i])) + decoding_biases[i], self.decoding_activations[i])

        # reconstruction loss
        if self.loss[0] == 'rmse':
            loss = tf.sqrt(tf.reduce_mean(tf.square(tf.subtract(x_, status))))
        elif self.loss[0] == 'cross-entropy':
            loss = tf.reduce_mean(
                tf.nn.sigmoid_cross_entropy_with_logits(logits=status, labels=x_))
        train_op = tf.train.AdamOptimizer(self.lr).minimize(loss) #TODO: Use also AdamOptimizer, GradientDescentOptimizer

        sess.run(tf.global_variables_initializer())#initialize_all_variables())
        for i in range(self.epoch[0]):
            b_x, b_x_ = utils.get_batch(masked_data_x, data_x, self.batch_size)
            sess.run(train_op, feed_dict={x: b_x, x_: b_x_})
            if (i + 1) % self.print_step == 0:
                l = sess.run(loss, feed_dict={x: masked_data_x, x_: data_x})
                print('epoch {0}: global loss = {1}'.format(i, l))

        for i in range(self.depth):
            self.weights[i] = sess.run(weights[i])
            self.biases[i] = sess.run(biases[i])
            self.decoding_biases[i] = sess.run(decoding_biases[i])

    def encode(self, data):
        tf.reset_default_graph()
        sess = tf.Session()
        x = tf.constant(data, dtype=tf.float32)
        for w, b, a in zip(self.weights, self.biases, self.activations):
            weight = tf.constant(w, dtype=tf.float32)
            bias = tf.constant(b, dtype=tf.float32)
            layer = tf.matmul(x, weight) + bias
            x = self.activate(layer, a)
        return x.eval(session=sess)

    def decode(self, data):
        tf.reset_default_graph()
        sess = tf.Session()
        x = tf.constant(data, dtype=tf.float32)
        for w, b, a in zip(self.weights[::-1], self.decoding_biases[::-1], self.decoding_activations[::-1]):
            weight = tf.transpose(tf.constant(w, dtype=tf.float32))
            bias = tf.constant(b, dtype=tf.float32)
            layer = tf.matmul(x, weight) + bias
            x = self.activate(layer, a)
        return x.eval(session=sess)

    def test(self, data, samples_shown=1, threshold=0.0):
        data_ = self.decode(self.encode(data))
        rmse = np.sqrt(np.mean(np.power(data - data_, 2)))
        print('Test rmse: {0}'.format(rmse))
        for i in np.random.choice(len(data), samples_shown):
            print('Sample {0}'.format(i))
            for d, d_ in zip(data[i], data_[i]):
                if(abs(d-d_) >= threshold):
                    print('\tOriginal: {0:.2f} --- Reconstructed: {1:.2f} --- Difference: {2:.2f}'.format(d,d_,d-d_))

    def fit_encode(self, x):
        self.fit(x)
        self.finetune(x)
        return self.encode(x)

    def run(self, data_x, data_x_, hidden_dim, activation, decoding_activation, loss, lr,
            print_step, epoch, batch_size=100):
        tf.reset_default_graph()
        input_dim = len(data_x[0])
        sess = tf.Session()
        x = tf.placeholder(dtype=tf.float32, shape=[None, input_dim], name='x')
        x_ = tf.placeholder(dtype=tf.float32, shape=[None, input_dim], name='x_')

        encode = {'weights': tf.Variable(tf.truncated_normal([input_dim, hidden_dim], dtype=tf.float32)),
                  'biases': tf.Variable(tf.truncated_normal([hidden_dim],dtype=tf.float32))}
        decode = {'biases': tf.Variable(tf.truncated_normal([input_dim],dtype=tf.float32)),
                  'weights': tf.transpose(encode['weights'])}

        encoded = self.activate(tf.matmul(x, encode['weights']) + encode['biases'], activation)
        decoded = self.activate(tf.matmul(encoded, decode['weights']) + decode['biases'], decoding_activation)

        # reconstruction loss
        if loss == 'rmse':
            loss = tf.sqrt(tf.reduce_mean(tf.square(tf.subtract(x_, decoded))))
        elif loss == 'cross-entropy':
            loss = tf.reduce_mean(
                tf.nn.sigmoid_cross_entropy_with_logits(logits=decoded, labels=x_))
        train_op = tf.train.AdamOptimizer(lr).minimize(loss) #TODO: Use also AdamOptimizer, GradientDescentOptimizer

        sess.run(tf.global_variables_initializer())#initialize_all_variables())
        for i in range(epoch):
            b_x, b_x_ = utils.get_batch(data_x, data_x_, batch_size)
            sess.run(train_op, feed_dict={x: b_x, x_: b_x_})
            if (i + 1) % print_step == 0:
                l = sess.run(loss, feed_dict={x: data_x, x_: data_x_})
                print('epoch {0}: global loss = {1}'.format(i, l))
        # debug
        # print('Decoded', sess.run(decoded, feed_dict={x: self.data_x_})[0])
        self.weights.append(sess.run(encode['weights']))
        self.biases.append(sess.run(encode['biases']))
        self.decoding_biases.append(sess.run(decode['biases']))
        return sess.run(encoded, feed_dict={x: data_x_})

    def activate(self, linear, name):
        if name == 'sigmoid':
            return tf.nn.sigmoid(linear, name='encoded')
        elif name == 'softmax':
            return tf.nn.softmax(linear, name='encoded')
        elif name == 'softplus':
            return tf.nn.softplus(linear, name='encoded')
        elif name == 'linear':
            return linear
        elif name == 'tanh':
            return tf.nn.tanh(linear, name='encoded')
        elif name == 'relu':
            return tf.nn.relu(linear, name='encoded')