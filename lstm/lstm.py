from __future__ import print_function
import numpy as np
import tensorflow as tf
import time
from tensorflow.contrib import rnn

allowed_activations = ['sigmoid', 'tanh', 'softmax', 'relu', 'linear', 'softplus']
allowed_losses = ['rmse', 'softmax-cross-entropy', 'sparse-softmax-cross-entropy', 'weighted-sparse-softmax-cross-entropy', 'sigmoid-cross-entropy']
allowed_initializers = ['uniform', 'xavier']
allowed_optimizers = ['gradient-descent','adam']

def shift_padding(X, X_, max_sequence_length): #TODO fix truncate case
    assert len(X) > 0, "Dataset should have at least one timeseries"
    assert len(X) == len(X_), "Input and classes should have the same length"
    assert max_sequence_length > 0, "Max sequence length should be positive" 
    dim = len(X)
    input_size = len(X[0][0])
    class_size = len(X_[0][0])
    newX = []
    newX_ = []
    sequence_length = []

    for index in range(len(X_)):
        start = 0
        end = 0

        if(np.max(X_[index]) > 0): #at least 1 valid class
            start = np.where(np.array([np.max(wave) for wave in X_[index]]) > 0)[0][0]
            end = np.where(np.array([np.max(wave) for wave in X_[index]]) > 0)[0][-1:][0]
        if(end > max_sequence_length):
            end = max_sequence_length
        length = end - start

        shifted_classes = np.concatenate((X_[index][1:], [np.zeros(class_size)]))
        waves_indexes = np.arange(start, end)
        if(length < max_sequence_length):
            tmpX = np.concatenate((X[index][waves_indexes], [np.zeros(input_size) for i in range(length, max_sequence_length)]))
            tmpX_ = np.concatenate((shifted_classes[waves_indexes], [np.zeros(class_size) for i in range(length, max_sequence_length)]))
        else:
            tmpX = np.array(X[index][waves_indexes])
            tmpX_ = np.array(shifted_classes[waves_indexes])
        
        if length > 0:
            newX.append(tmpX)
            newX_.append(tmpX_)
            sequence_length.append(length)
    return np.array(newX), np.array(newX_), np.array(sequence_length)

def get_batches(X, X_, lengths, size): 
    assert size > 0, "Size should positive"
    idx = np.random.choice(len(X), size, replace=False)
    return X[idx], X_[idx], lengths[idx]

def get_sequential_batches(X, X_, lengths, start, size):
    assert size > 0, "Size should positive"
    assert start >= 0, "Start should not be negative"   
    return X[start:start+size], X_[start:start+size], lengths[start:start+size]

class Lstm:
    def assertions(self):
        global allowed_activations, allowed_losses
        assert self.max_sequence_length > 0, "Incorrect max sequence length"
        assert self.activation_function in allowed_activations, "Incorrect activation given."
        assert self.loss_function in allowed_losses, "Incorrect loss given."
        assert self.initialization_function in allowed_initializers, "Incorrect initializer given."
        assert self.optimization_function in allowed_optimizers, "Incorrect optimizer given."
        #assert self.cost_mask.shape[0] == self.output_size, "Invalid cost mask length."

    def __init__(self, max_sequence_length, input_size, state_size, output_size, loss_function, activation_function='tanh',
                initialization_function='uniform', optimization_function='gradient-descent', epoch=1000, learning_rate=0.01, batch_size=16, cost_mask=np.array([])):
        self.max_sequence_length = max_sequence_length
        self.input_size = input_size
        self.state_size = state_size
        self.output_size = output_size
        self.activation_function = activation_function
        self.loss_function = loss_function
        self.initialization_function = initialization_function
        self.optimization_function = optimization_function
        self.epoch = epoch
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        if(not len(cost_mask) > 0 or not self.output_size > 0): #TODO handle output_size <= 0
            cost_mask = np.ones(self.output_size)        
        self.cost_mask = tf.reshape(tf.constant(np.tile(cost_mask, batch_size * max_sequence_length), dtype=tf.float32), (batch_size, max_sequence_length, output_size))
        self.assertions()
        self._create_model()

    def _create_model(self):
        self.x = tf.placeholder(tf.float32, [self.batch_size, self.max_sequence_length, self.input_size]) #batch - timeseries - input vector
        self.y = tf.placeholder(tf.float32, [self.batch_size, self.max_sequence_length, self.output_size]) #batch - timeseries - class vector
        self.sequence_length = tf.placeholder(tf.int32, [self.batch_size]) #batch - timeseries length TODO is it ok?
        initializer = self.get_initializater(self.initialization_function)
        activation = self.get_activation(self.activation_function)
        
        cell = tf.nn.rnn_cell.LSTMCell(num_units=self.state_size, num_proj=self.output_size, initializer=initializer, activation=activation) #TODO check if all the gates are present

        outputs, _ = tf.nn.dynamic_rnn(cell=cell, inputs=self.x, sequence_length=self.sequence_length, dtype=tf.float32)

        self.loss = self.get_loss(logits=outputs, labels=self.y, name=self.loss_function, lengths=self.sequence_length)
        self.optimizer = self.get_optimizer(name=self.optimization_function, learning_rate=self.learning_rate, loss=self.loss)

        correct_prediction = tf.equal(tf.argmax(outputs, 2), tf.argmax(self.y, 2))
        self.accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

        #Test
        self.testLogits = tf.reshape(outputs, (-1, self.output_size))
        self.testLabels = tf.reshape(self.y, (-1, self.output_size))

        #Saver
        self.saver = tf.train.Saver()
        
        #Tensorboard
        #writer = tf.summary.FileWriter("C:\\Users\\danie\\Documents\\SDA-LSTM\\logs", graph=tf.get_default_graph())
    
    def train(self, X, Y, lengths):
        batches_per_epoch = int(len(X) / self.batch_size)
        initial_learning_rate = self.learning_rate

        with tf.Session() as sess:
            sess.run(tf.global_variables_initializer())
            for epoch in range(self.epoch):
                avg_loss = 0.
                avg_accuracy = 0.
                self.learning_rate = (initial_learning_rate * 10) / (10 * (epoch + 1))
                for i in range(batches_per_epoch):
                    batches_x, batches_y, batches_length = get_sequential_batches(X, Y, lengths, i * self.batch_size, self.batch_size)
                    sess.run(self.optimizer, feed_dict={self.x: batches_x, self.y: batches_y, self.sequence_length: batches_length})
                    loss, accuracy = sess.run([self.loss, self.accuracy], feed_dict={self.x: batches_x, self.y: batches_y, self.sequence_length: batches_length})
                    avg_loss += loss
                    avg_accuracy += accuracy
                avg_loss /= batches_per_epoch
                avg_accuracy /= batches_per_epoch
                print("Epoch {0}: loss = {1:.6f}, accuracy = {2:.2f}%".format(epoch, avg_loss, avg_accuracy * 100))
            self.saver.save(sess, './checkpoint',0)
    
    def test(self, X, Y, lengths):
        batches_per_epoch = int(len(X) / self.batch_size)

        with tf.Session() as sess:
            self.saver.restore(sess, tf.train.latest_checkpoint('.'))
            avg_accuracy = 0.
            avg_loss = 0.
            counters = [[0 for i in range(self.output_size)] for j in range(self.output_size)]
            for i in range(batches_per_epoch):
                batches_x, batches_y, batches_length = get_sequential_batches(X, Y, lengths, i * self.batch_size, self.batch_size)  
                loss, accuracy, testLogits, testLabels = sess.run([self.loss, self.accuracy, self.testLogits, self.testLabels], feed_dict={self.x: batches_x, self.y: batches_y, self.sequence_length: batches_length})            
                
                for i in range(len(testLabels)):
                        label_idx = np.argmax(testLabels[i])
                        logit_idx = np.argmax(testLogits[i])
                        counters[label_idx][logit_idx] += 1
                
                avg_loss += loss
                avg_accuracy += accuracy
            [print("class {0}, accuracy = {1:.2f}, values =".format(i+1, counters[i][i] / np.sum(counters[i])), counters[i]) for i in range(len(counters))]
            avg_loss /= batches_per_epoch
            avg_accuracy /= batches_per_epoch
            print("Test: loss = {0:.6f}, accuracy = {1:.2f}%".format(avg_loss, avg_accuracy * 100))

    def get_activation(self, name):
        if name == 'sigmoid':
            return tf.nn.sigmoid
        elif name == 'softmax':
            return tf.nn.softmax
        elif name == 'softplus':
            return tf.nn.softplus
        elif name == 'linear':
            return linear
        elif name == 'tanh':
            return tf.nn.tanh
        elif name == 'relu':
            return tf.nn.relu

    def get_loss(self, logits, labels, name, lengths=None):
        if name == 'rmse':
            return tf.sqrt(tf.reduce_mean(tf.square(tf.subtract(labels, logits))))
        elif name == 'softmax-cross-entropy':
            return tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=logits, labels=labels))
        elif name == 'sparse-softmax-cross-entropy':
            return tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(logits=logits, labels=tf.argmax(labels, 2)))
        elif name == 'sigmoid-cross-entropy':
            return tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(logits=logits, labels=labels))
        elif name == 'weighted-sparse-softmax-cross-entropy':
            cross_entropy = tf.nn.sparse_softmax_cross_entropy_with_logits(logits=logits, labels=tf.argmax(labels, 2))
            cross_entropy = tf.multiply(cross_entropy, tf.reduce_sum(tf.multiply(self.cost_mask, labels), 2))
            cross_entropy = tf.reduce_sum(cross_entropy, reduction_indices=1)
            cross_entropy = tf.divide(cross_entropy, tf.cast(lengths, dtype=tf.float32))
            return tf.reduce_mean(cross_entropy)

    def get_initializater(self, name):
        if name == 'uniform':
            return tf.random_uniform_initializer(-1, 1)
        elif name == 'xavier':
            return tf.contrib.layers.xavier_initializer()

    def get_optimizer(self, name, learning_rate, loss):
        if name == 'gradient-descent':
            return tf.train.GradientDescentOptimizer(learning_rate=learning_rate).minimize(loss)
        elif name == 'adam':
            return tf.train.AdamOptimizer(learning_rate=learning_rate).minimize(loss)

#cost_mask = np.array([1., 8., 15., 23., 34., 36., 92., 162., 260., 455.]) / 10 #/ 1086
cost_mask = np.array([1., 8., 15., 23., 34., 36., 92., 92., 92., 92.]) / 10 #/ 1086

#Loading
e_values1 = np.load("../data/e_records.npy")
e_classes1 = np.load("../data/e_classes.npy")
t_values1= np.load("../data/t_records.npy")
t_classes1 = np.load("../data/t_classes.npy")

max_length = 5

#Add classes to training inputs
e_values1 = np.concatenate((e_values1, e_classes1), axis=2)
t_values1 = np.concatenate((t_values1, t_classes1), axis=2)

#Shift+pad
e_values, e_classes, e_lengths = shift_padding(e_values1, e_classes1, max_length)
t_values, t_classes, t_lengths = shift_padding(t_values1, t_classes1, max_length)

#Concatenate datasets
values = np.concatenate((e_values, t_values))
classes = np.concatenate((e_classes, t_classes))
lengths = np.concatenate((e_lengths, t_lengths))

#LSTM definition
lstm = Lstm(max_sequence_length=max_length, input_size=len(values[0][0]), state_size=50, output_size=len(classes[0][0]), 
            loss_function='weighted-sparse-softmax-cross-entropy', initialization_function='xavier', 
            optimization_function='gradient-descent', learning_rate=0.1, batch_size=32, epoch=10, cost_mask=cost_mask)

#Training + testing
lstm.train(values, classes, lengths)
lstm.test(values, classes, lengths)