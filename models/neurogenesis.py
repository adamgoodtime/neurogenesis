import numpy as np


class Synapses():
    def __init__(self, pre, post, freq, f_width=0.3, weight=1.):
        self.pre = pre
        self.post = post
        self.freq = freq
        self.f_width = f_width
        self.weight = weight

    def response(self, input):
        return self.weight * max(1. - abs((input - self.freq) / self.f_width), 0)


class Neuron():
    def __init__(self, neuron_label, connections, f_width=0.3):
        self.neuron_label = neuron_label
        self.f_width = f_width
        self.synapses = {}
        self.synapse_count = len(connections)
        for pre in connections:
            freq = connections[pre]
            self.synapses[pre] = []
            self.synapses[pre].append(Synapses(pre + '0', neuron_label, freq,
                                               f_width=self.f_width))

    def add_connection(self, pre, freq, weight=1.):
        self.synapse_count += 1
        if pre not in self.synapses:
            self.synapses[pre] = []
        self.synapses[pre].append(Synapses(pre + '{}'.format(len(self.synapses[pre])),
                                           self.neuron_label, freq,
                                           weight=weight,
                                           f_width=self.f_width))

    def add_multiple_connections(self, connections):
        for pre in connections:
            freq = connections[pre]
            if pre not in self.synapses:
                self.synapses[pre] = []
            self.synapses[pre].append(Synapses(pre + '{}'.format(len(self.synapses[pre])),
                                               self.neuron_label, freq,
                                               f_width=self.f_width))
            self.synapse_count += 1

    def response(self, activations):
        if not self.synapse_count:
            return 0.
        response = 0.
        for pre in activations:
            freq = activations[pre]
            if pre in self.synapses:
                for synapse in self.synapses[pre]:
                    response += synapse.response(freq)
        return response / self.synapse_count


class Network():
    def __init__(self, number_of_classes, seed_class, seed_features,
                 error_threshold=0.1,
                 f_width=0.3,
                 activation_threshold=0.01):
        self.error_threshold = error_threshold
        self.f_width = f_width
        self.activation_threshold = activation_threshold
        self.neurons = {}
        self.number_of_classes = number_of_classes
        # add seed neuron
        self.neurons['seed{}'.format(seed_class)] = Neuron('seed{}'.format(seed_class),
                                                           self.convert_inputs_to_activations(seed_features),
                                                           f_width=f_width)
        # add outputs
        for output in range(number_of_classes):
            self.add_neuron({}, 'out{}'.format(output))
        # connect seed neuron to seed class
        self.neurons['out{}'.format(seed_class)].add_connection('seed{}'.format(seed_class),
                                                                freq=1.)
        self.hidden_neuron_count = 1
        self.layers = 2

    def add_neuron(self, connections, neuron_label=''):
        if neuron_label == '':
            neuron_label = 'n{}'.format(self.hidden_neuron_count)
            self.hidden_neuron_count += 1
        self.neurons[neuron_label] = Neuron(neuron_label, connections,
                                            f_width=self.f_width)
        return neuron_label
        #### find a way to know whether you need to add a layer
        # for pre in connections:
        #     if 'in' not in pre

    def connect_neuron(self, neuron_label, connections):
        self.neurons[neuron_label].add_multiple_connections(connections)

    def response(self, activations):
        # for i in range(self.layers):
        for neuron in self.neurons:
            response = self.neurons[neuron].response(activations)
            activations[self.neurons[neuron].neuron_label] = response
        outputs = ['out{}'.format(i) for i in range(self.number_of_classes)]
        for neuron in outputs:
            response = self.neurons[neuron].response(activations)
            activations[self.neurons[neuron].neuron_label] = response
        return activations

    def convert_inputs_to_activations(self, inputs):
        acti = {}
        for idx, ele in enumerate(inputs):
            acti['in{}'.format(idx)] = ele
        return acti

    def remove_output_neurons(self, activations):
        neural_activations = {}
        for neuron in activations:
            if 'out' not in neuron:
                if activations[neuron] > self.activation_threshold:
                    neural_activations[neuron] = activations[neuron]
        return neural_activations

    def error_driven_neuro_genesis(self, activations, output_error):
        if np.max(np.abs(output_error)) > self.error_threshold:
            activations = self.remove_output_neurons(activations)
            neuron_label = self.add_neuron(activations)
            for output, error in enumerate(output_error):
                if abs(error) > self.error_threshold:
                    self.neurons['out{}'.format(output)].add_connection(neuron_label,
                                                                        freq=1.,
                                                                        weight=-error)





