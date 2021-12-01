import numpy as np
import random
import operator
import scipy.stats as st
from models.convert_network import create_network, build_network
from tests.backprop_from_activations import forward_propagate, forward_matrix_propagate


class Synapses():
    def __init__(self, pre, post, freq, f_width=0.3, weight=1., reward_decay=1., sensitivity=0.):
        self.pre = pre
        self.post = post
        self.freq = freq
        self.f_width = f_width
        self.weight = weight
        self.reward_decay = reward_decay
        self.age = 0.
        self.age_multiplier = 1. #/ self.maturation
        self.sensitivity = sensitivity
        self.activity = 0.
        self.reward = 0.1

    def contribution(self):
        return self.sensitivity * self.freq

    def age_weight(self):
        if self.age == self.maturation:
            return
        self.age += 1.
        self.age = min(self.age, self.maturation)
        self.age_multiplier = 1. + self.age#(self.age / self.maturation)
        
    def update_reward(self, reward):
        self.reward = ((1. - self.reward_decay) * self.activity * reward) + (self.reward_decay * self.reward)
        if self.reward < 0:
            print("I'm sorry, what?")
        return self.reward

    def reinforce(self, reward):
        delta_w = reward * self.activity
        if delta_w > 0:
            print("updating - old:", self.weight, "- new:", self.weight + (delta_w * self.reward_decay))
        self.weight += delta_w * self.reward_decay

    def response(self, input):
        # self.activity = st.norm.cdf(-abs((input - self.freq) / self.f_width)) * 2
        self.activity = max(1. - abs((input - self.freq) / self.f_width), 0) #* self.age_multiplier
        return self.activity * self.weight



class Neuron():
    def __init__(self, neuron_label, connections, sensitivities, weights=None, f_width=0.3,
                 input_dimensions=None, reward_decay=1., width_noise=0., x=None, y=None):
        self.neuron_label = neuron_label
        self.f_width = f_width
        self.width_noise = width_noise
        self.synapses = {}
        self.synapse_count = 0
        self.input_dimensions = input_dimensions
        self.visualisation = None
        self.reward_decay = reward_decay
        self.activity = 0
        self.output = -1
        self.correctness = 0.
        self.connections = connections
        self.x = x
        self.y = y
        if not weights:
            weights = {}
        for pre in connections:
            # if pre not in weights:
            #     weights[pre] = 1.
            freq = connections[pre]
            self.add_connection(pre, freq, sensitivities=sensitivities, weight=1.)
            # self.synapses[pre] = []
            # self.synapses[pre].append(Synapses(pre + '0', neuron_label, freq,
            #                                    f_width=self.f_width,
            #                                    weight=weights[pre]))

    def add_connection(self, pre, freq, sensitivities, weight=1., reward_decay=1., width=None):
        if width == None:
            width = self.f_width + np.random.normal(scale=self.width_noise)
        self.synapse_count += 1
        if pre not in self.synapses:
            self.synapses[pre] = []
        # if 'out' in self.neuron_label:
        #     sensitivities[pre] = 1.
        self.synapses[pre].append(Synapses(pre + '{}'.format(len(self.synapses[pre])),
                                           self.neuron_label, freq,
                                           weight=weight,
                                           f_width=width,
                                           reward_decay=self.reward_decay))
        
    def remove_connection(self, pre, idx):
        del self.synapses[pre][idx]
        if len(self.synapses[pre]) == 0:
            del self.synapses[pre]
        self.synapse_count -= 1

    def record_correctness(self, correctness):
        # self.correctness = ((1. - self.reward_decay) * self.activity * correctness) + \
        #                    (self.reward_decay * self.correctness)
        self.correctness += self.activity * correctness
        # print(self.neuron_label, self.activity)
        return self.correctness

    def response(self, activations, x=None, y=None):
        if not self.synapse_count:
            return 0.
        response = 0.
        active_synapse_weight = 0
        for pre in self.synapses:  # do as an intersection of sets? inter = activations.keys() & self.synapses.keys()
            if pre in activations:
                freq = activations[pre]
                for synapse in self.synapses[pre]:
                    response += synapse.response(freq)
                    active_synapse_weight += 1.#synapse.weight
        if active_synapse_weight and 'out' not in self.neuron_label:
            self.activity = response / active_synapse_weight
        else:
            self.activity = response
        if x and y and self.x and self.y:
            x_value = max(1. - abs((self.x - x) / self.f_width), 0)
            y_value = max(1. - abs((self.y - y) / self.f_width), 0)
            self.activity *= x_value * y_value
        return self.activity


class Network():
    def __init__(self, number_of_classes, number_of_inputs, seed_class=None, seed_features=None, seeds=None,
                 error_threshold=0.1,
                 f_width=0.3,
                 width_noise=0.,
                 activation_threshold=0.01,
                 maximum_total_synapses=20,
                 max_hidden_synapses=100,
                 activity_decay_rate=0.9,
                 always_inputs=True,
                 old_weight_modifier=1.,
                 input_dimensions=None,
                 reward_decay=1.,
                 delete_neuron_type='RL',
                 fixed_hidden_ratio=0.1,
                 activity_init=1.0,
                 replaying=True,
                 hidden_threshold=0.9,
                 conv_size=4):
        self.error_threshold = error_threshold
        self.f_width = f_width
        self.width_noise = width_noise
        self.activation_threshold = activation_threshold
        self.hidden_neuron_count = 0
        self.deleted_neuron_count = 0
        self.maximum_total_synapses = maximum_total_synapses
        self.max_hidden_synapses = max_hidden_synapses
        self.synapse_count = 0
        self.synapse_rewards = []
        self.neuron_rewards = {}
        self.always_inputs = always_inputs
        self.old_weight_modifier = old_weight_modifier
        self.current_importance = 1.
        self.input_dimensions = input_dimensions
        self.reward_decay = reward_decay
        self.delete_neuron_type = delete_neuron_type
        self.fixed_hidden_ratio = fixed_hidden_ratio
        self.activity_init = activity_init
        self.replaying = replaying
        self.hidden_threshold = hidden_threshold
        self.conv_size = conv_size
        self.correctness = [{} for i in range(number_of_classes)]

        self.neurons = {}
        self.neuron_activity = {}
        self.neuron_selectivity = {}
        self.neuron_response = {}
        self.neuron_connectedness = {}
        self.deleted_outputs = {}
        self.activity_decay_rate = activity_decay_rate
        self.number_of_classes = number_of_classes

        self.procedural = []
        self.procedural_value = [0. for i in range(number_of_classes)]
        self.n_procedural_out = 0
        # add seed neuron
        # self.neurons['seed{}'.format(seed_class)] = Neuron('seed{}'.format(seed_class),
        # self.neurons['n0'] = Neuron('n0',
        #                             self.convert_inputs_to_activations(seed_features),
        #                             f_width=f_width)
        self.number_of_inputs = number_of_inputs #len(seed_features[0])
        for i in range(self.number_of_inputs):
            self.neuron_activity['in{}'.format(i)] = 0.
        # add outputs
        for output in range(number_of_classes):
            self.add_neuron({}, 'out{}'.format(output))
        # connect seed neuron to seed class
        if seeds:
            self.add_seed(seeds, seed_class, seed_features)
        # self.neurons['out{}'.format(seed_class)].add_connection('seed{}'.format(seed_class),
        self.layers = 2

    def add_seed(self, seeds, seed_classes, seed_features):
        input_response = {}
        seed_count = 0
        for seed in seeds:
            converted_inputs = self.convert_inputs_to_activations(seed_features[seed])
            for feat in converted_inputs:
                if feat not in input_response:
                    input_response[feat] = 0.
                input_response[feat] += converted_inputs[feat]
            features = seed_features[seed]
            seed_class = seed_classes[seed]
            neuron_label = self.add_neuron(converted_inputs, seeding=True)
            self.neurons['out{}'.format(seed_class)].add_connection(neuron_label, freq=1.)
            self.neuron_connectedness[neuron_label] = 1
            seed_count += 1
            print("Added seed", seed_count, "/", len(seeds))
        for inp in input_response:
            input_response[inp] /= seed_count
            self.neuron_activity[inp] = input_response[inp]
        print("Completed adding seeds")


    def add_neuron(self, connections, neuron_label='', seeding=False, x=None, y=None):
        if self.max_hidden_synapses and not seeding:
            connections = self.limit_connections(connections)
        if neuron_label == '':
            neuron_label = 'n{}'.format(self.hidden_neuron_count)
            self.hidden_neuron_count += 1
        self.neurons[neuron_label] = Neuron(neuron_label, connections, self.neuron_selectivity,
                                            f_width=self.f_width,
                                            width_noise=self.width_noise,
                                            input_dimensions=self.input_dimensions,
                                            reward_decay=self.reward_decay,
                                            x=x, y=y)
        self.synapse_count += self.neurons[neuron_label].synapse_count
        if self.synapse_count > self.maximum_total_synapses:
            # self.delete_synapses(self.synapse_count - self.maximum_total_synapses)
            self.delete_neuron()
        # visualisation = self.visualise_neuron(neuron_label)
        hidden_activity = self.return_hidden_neurons(self.neuron_activity)
        self.neuron_response[neuron_label] = 0.
        if len(self.neuron_rewards) > 0:
            self.neuron_rewards[neuron_label] = sum(self.neuron_rewards.values()) / len(self.neuron_rewards)
        else:
            if 'out' not in neuron_label:
                self.neuron_rewards[neuron_label] = 0.
        if len(hidden_activity) != 0 and self.activity_decay_rate < 1.0:
            self.neuron_activity[neuron_label] = sum(hidden_activity.values()) / len(hidden_activity)
        else:
            self.neuron_activity[neuron_label] = self.activity_init
            # self.neuron_activity[neuron_label] = self.activity_init#self.neurons[neuron_label].response(connections)
        # self.neuron_selectivity[neuron_label] = -1.
        return neuron_label

    def delete_neuron(self, delete_type='RL'):
        # if 'n' not in delete_type:
        #     delete_type = self.delete_neuron_type
        if delete_type == 'old':
            oldest_neuron = 'n{}'.format(self.deleted_neuron_count)
            delete_neuron = oldest_neuron
        elif delete_type == 'new':
            # oldest_neuron = 'n{}'.format(self.deleted_neuron_count)
            delete_neuron = 'n{}'.format(self.hidden_neuron_count - 1)
        elif delete_type == 'quiet':
            quiet_neuron = min(self.return_hidden_neurons(self.neuron_selectivity).items(),
                               key=operator.itemgetter(1))[0]
            delete_neuron = quiet_neuron
        elif 'n' in delete_type:
            delete_neuron = delete_type
        elif delete_type == 'RL':
            delete_neuron = min(self.neuron_rewards.items(),
                               key=operator.itemgetter(1))[0]
        else:
            # synapse_count = [[key, self.neurons[key].synapse_count] for key in self.neurons]
            # unconnected_neuron = min(self.neuron_connectedness, key=operator.itemgetter(1))[0]
            unconnected_neuron = min(self.return_hidden_neurons(self.neuron_connectedness).items(),
                                     key=operator.itemgetter(1))[0]
            delete_neuron = unconnected_neuron
        if 'in' in delete_neuron or 'out' in delete_neuron:
            print("not sure what deleting does here")
        self.synapse_count -= self.neurons[delete_neuron].synapse_count
        if delete_neuron in self.correctness[self.neurons[delete_neuron].output]:
            del self.correctness[self.neurons[delete_neuron].output][delete_neuron]
        del self.neurons[delete_neuron]
        del self.neuron_activity[delete_neuron]
        if delete_neuron in self.neuron_selectivity:
            del self.neuron_selectivity[delete_neuron]
        del self.neuron_connectedness[delete_neuron]
        del self.neuron_rewards[delete_neuron]
        if delete_neuron in self.neuron_response:
            del self.neuron_response[delete_neuron]
        for neuron in self.neurons:
            if delete_neuron in self.neurons[neuron].synapses:
                del self.neurons[neuron].synapses[delete_neuron]
        for i in range(self.number_of_classes):
            if delete_neuron in self.neurons['out{}'.format(i)].synapses:
                self.synapse_count -= len(self.neurons['out{}'.format(i)].synapses[delete_neuron])
                del self.neurons['out{}'.format(i)].synapses[delete_neuron]
        self.deleted_neuron_count += 1

    def delete_synapses(self, amount):
        self.synapse_rewards.sort()
        for i in range(amount):
            neuron = self.synapse_rewards[0][1]
            pre = self.synapse_rewards[0][2]
            idx = self.synapse_rewards[0][3]
            self.neurons[neuron].remove_connection(pre, idx)
            del self.synapse_rewards[0]
            self.synapse_count -= 1
            if self.neurons[neuron].synapse_count == 0:
                self.delete_neuron(neuron)

    def count_synapses(self, connections):
        for pre in connections:
            if pre in self.neuron_connectedness:
                self.neuron_connectedness[pre] += 1
            else:
                self.neuron_connectedness[pre] = 1

    def process_selectivity(self, only_positive=False):
        input_selectivity = {}
        hidden_selectivity = {}
        for neuron in self.neuron_selectivity:
            if 'in' in neuron or 'p' in neuron:
                if len(self.procedural) >= 30:
                    if 'p' in neuron:
                        # if 'p2' in neuron or 'p3' in neuron:
                        input_selectivity[neuron] = abs(self.neuron_selectivity[neuron])
                else:
                    # if 'in' in neuron:
                    input_selectivity[neuron] = abs(self.neuron_selectivity[neuron])
                # input_selectivity[neuron] = abs(self.neuron_selectivity[neuron])
            elif 'out' not in neuron:
                if self.neuron_selectivity[neuron] == 1.:
                    print("da fuck")
                if only_positive:
                    hidden_selectivity[neuron] = self.neuron_selectivity[neuron]
                else:
                    hidden_selectivity[neuron] = abs(self.neuron_selectivity[neuron])
        return input_selectivity, hidden_selectivity

    def get_max_selectivity(self, selectivity, n_select, random_sampling=False):
        selected = 0
        if len(selectivity) == 0:
            return {}
        total_dic = {}
        if random_sampling:
            sample_dic = random.sample(selectivity.items(), min(n_select-selected, len(selectivity)))
            for key, v in sample_dic:
                total_dic[key] = v
            return total_dic
        ordered_dict = dict(sorted(selectivity.items(),
                                     # key=lambda dict_key: abs(self.neuron_selectivity[dict_key[0]]),
                                     key=operator.itemgetter(1),
                                     reverse=True))
        while selected < n_select and selected < len(selectivity):
            current_max = None
            selected_dic = {}
            for k, v in ordered_dict.items():
                if current_max is None or v > current_max:
                    current_max = v
                if v == current_max:
                    selected_dic[k] = v
                else:
                    break
            sample_dic = random.sample(selected_dic.items(), min(n_select-selected, len(selected_dic)))
            for key, v in sample_dic:
                total_dic[key] = v
                del ordered_dict[key]
            selected += len(sample_dic)
        return total_dic

    def limit_connections(self, connections, selectivity=False, thresholded=False, outlier=True, conv=False):
        if len(connections) <= min(self.max_hidden_synapses, self.number_of_inputs):
            return connections
        if conv:
            input_selectivity, hidden_selectivity = self.process_selectivity()
            selected_input = self.get_max_selectivity(input_selectivity, 1)
            input_id = int(list(selected_input.items())[0][0].replace('in', ''))
            ids = np.array(range(self.number_of_inputs)).reshape(self.input_dimensions)
            y, x = np.where(ids == input_id)
            y = y[0]
            x = x[0]
            if x - self.conv_size < 0:
                x = self.conv_size
            elif x + self.conv_size >= self.input_dimensions[0]:
                x = self.input_dimensions[0] - self.conv_size - 1
            if y - self.conv_size < 0:
                y = self.conv_size
            elif y + self.conv_size >= self.input_dimensions[1]:
                y = self.input_dimensions[1] - self.conv_size - 1
            input_id = ids[y][x]
            selected_input = {}
            for i in range(-self.conv_size, self.conv_size+1):
                for j in range(-self.conv_size, self.conv_size+1):
                    new_id = (input_id + j) + (i * self.input_dimensions[0])
                    selected_input['in{}'.format(new_id)] = connections['in{}'.format(new_id)]
            pruned_connections = {}
            for pre in selected_input:
                pruned_connections[pre] = connections[pre]
            if self.hidden_neuron_count:
                number_of_hidden = int(min(self.hidden_neuron_count - self.deleted_neuron_count,
                                           self.fixed_hidden_ratio * self.max_hidden_synapses))
                # using outlier for hidden selection
                hidden_response = self.return_hidden_neurons(self.neuron_response)
                ave_response = sum(hidden_response.values()) / len(hidden_response)
                relative_response = {}
                for neuron in hidden_response:
                    relative_response[neuron] = abs(hidden_response[neuron] - ave_response)
                selected_hidden = self.get_max_selectivity(relative_response,
                                                           number_of_hidden)
                for pre in selected_hidden:
                    pruned_connections[pre] = connections[pre]
            return pruned_connections
        if selectivity:
            pruned_connections = {}
            input_selectivity, hidden_selectivity = self.process_selectivity()
            number_of_hidden = int(min(self.hidden_neuron_count - self.deleted_neuron_count,
                                        self.fixed_hidden_ratio * self.max_hidden_synapses))
            if thresholded:
                for neuron in hidden_selectivity:
                    # if self.neuron_response[neuron] > self.hidden_threshold or \
                    #         self.neuron_response[neuron] < 1. - self.hidden_threshold:
                    if self.neuron_response[neuron] < 1. - self.hidden_threshold:
                        pruned_connections[neuron] = connections[neuron]
                    if len(pruned_connections) >= self.max_hidden_synapses:
                        break
            elif outlier and self.hidden_neuron_count:
                hidden_response = self.return_hidden_neurons(self.neuron_response)
                ave_response = sum(hidden_response.values()) / len(hidden_response)
                relative_response = {}
                for neuron in hidden_response:
                    relative_response[neuron] = abs(hidden_response[neuron] - ave_response)
                selected_hidden = self.get_max_selectivity(relative_response,
                                                           number_of_hidden)
                for pre in selected_hidden:
                    pruned_connections[pre] = connections[pre]
            else:
                selected_hidden = self.get_max_selectivity(hidden_selectivity,
                                                           number_of_hidden)
                for pre in selected_hidden:
                    pruned_connections[pre] = connections[pre]
            selected_input = self.get_max_selectivity(input_selectivity,
                                                      self.max_hidden_synapses - len(pruned_connections))
            for pre in selected_input:
                pruned_connections[pre] = connections[pre]
            return pruned_connections
        else:
            # print("add thresholded selection here here")
            no_hidden = self.remove_hidden_neurons(connections)
            return dict(random.sample(list(no_hidden.items()),
                                      min(self.max_hidden_synapses,
                                          len(no_hidden))))

    def response(self, activations, replay=False, x=None, y=None):
        # for i in range(self.layers):
        response = activations
        for neuron in self.neurons:
            response[neuron] = self.neurons[neuron].response(activations, x, y)
            # line below can be compressed?
            activations[self.neurons[neuron].neuron_label] = response[neuron]
        for neuron in self.remove_output_neurons(activations, cap=False):
            if neuron not in self.neuron_activity:
                if self.activity_decay_rate < 1.0:
                    hidden_activity = self.return_hidden_neurons(activations)
                    self.neuron_activity[neuron] = sum(hidden_activity.values()) / len(hidden_activity)
                else:
                    self.neuron_activity[neuron] = self.activity_init
            if self.replaying:
                if replay:
                    self.neuron_selectivity[neuron] = response[neuron] - self.neuron_activity[neuron]
                self.neuron_activity[neuron] = response[neuron]
            else:
                self.neuron_selectivity[neuron] = response[neuron] - self.neuron_activity[neuron]
                self.neuron_response[neuron] = response[neuron]
                self.neuron_activity[neuron] = (self.neuron_activity[neuron] * self.activity_decay_rate) + \
                                               (response[neuron] * (1. - self.activity_decay_rate))
                # self.neuron_selectivity[neuron] = response[neuron] - self.neuron_activity[neuron]
        outputs = ['out{}'.format(i) for i in range(self.number_of_classes)]
        for out, neuron in enumerate(outputs):
            response = self.neurons[neuron].response(activations)
            activations[self.neurons[neuron].neuron_label] = response + self.procedural_value[out]
        return activations

    def record_correctness(self, correct_output):
        for neuron in self.neurons:
            if 'out' not in neuron and 'in' not in neuron:
                if self.neurons[neuron].output == correct_output:
                    val = self.neurons[neuron].record_correctness(1)
                else:
                    val = self.neurons[neuron].record_correctness(-1)
                self.correctness[self.neurons[neuron].output][neuron] = val
        return self.correctness

    def reinforce_synapses(self, reward, only_output=True, correct_output=0):
        self.synapse_rewards = []
        if only_output:
            for i in range(self.number_of_classes):
                neuron = 'out{}'.format(i)
                if i == correct_output:
                    syn_reward = 1.#reward
                else:
                    syn_reward = -1#reward
                for pre in self.neurons[neuron].synapses:
                    for syn in self.neurons[neuron].synapses[pre]:
                        syn_r = syn.reinforce(syn_reward)
                        self.synapse_rewards.append([syn_r, neuron, pre, self.neurons[neuron].synapses[pre].index(syn)])
        else:
            for neuron in self.neurons:
                for pre in self.neurons[neuron].synapses:
                    for syn in self.neurons[neuron].synapses[pre]:
                        syn_r = syn.update_reward(reward)
                        self.synapse_rewards.append([syn_r, neuron, pre, self.neurons[neuron].synapses[pre].index(syn)])
        return self.synapse_rewards

    def reinforce_neurons(self, reward):
        # self.neuron_rewards = []
        for neuron in self.neurons:
            if 'out' not in neuron and 'in' not in neuron:
                if neuron in self.neuron_rewards and neuron in self.neuron_response:
                    self.neuron_rewards[neuron] = ((1. - self.reward_decay) * self.neuron_response[neuron] * reward) \
                                                  + (self.reward_decay * self.neuron_rewards[neuron])
                # else:
                #     if neuron not in self.deleted_outputs: ### check this
                #         self.neuron_rewards[neuron] = sum(self.neuron_rewards.values()) / len(self.neuron_rewards)
        return self.neuron_rewards

    def remove_worst_output(self):
        delete_neuron = min(self.neuron_rewards.items(),
                            key=operator.itemgetter(1))[0]
        self.deleted_outputs[delete_neuron] = True
        del self.neuron_rewards[delete_neuron]
        for i in range(self.number_of_classes):
            if delete_neuron in self.neurons['out{}'.format(i)].synapses:
                self.synapse_count -= 1
                del self.neurons['out{}'.format(i)].synapses[delete_neuron]

    def convert_inputs_to_activations(self, inputs):
        self.procedural_value, all_p = self.procedural_output(inputs)
        acti = {}
        for idx, ele in enumerate(inputs):
            acti['in{}'.format(idx)] = ele
        if len(self.procedural) > 0:
            for idx, ele in enumerate(all_p):
                acti['p{}'.format(idx)] = ele
        return acti

    def return_hidden_neurons(self, activations, cap=True):
        neural_activations = {}
        for neuron in activations:
            if 'out' not in neuron and 'in' not in neuron:
                neural_activations[neuron] = activations[neuron]
        return neural_activations

    def remove_output_neurons(self, activations, cap=False):
        neural_activations = {}
        for neuron in activations:
            if 'out' not in neuron:
                if cap:
                    if activations[neuron] >= self.activation_threshold:
                        neural_activations[neuron] = activations[neuron]
                else:
                    neural_activations[neuron] = activations[neuron]
        return neural_activations

    def age_output_synapses(self, reward=True):
        if reward:
            weight_modifier = self.old_weight_modifier
        else:
            weight_modifier = 1. / self.old_weight_modifier
        for i in range(self.number_of_classes):
            for synapse in self.neurons['out{}'.format(i)].synapses:
                for syn in self.neurons['out{}'.format(i)].synapses[synapse]:
                    syn.age_weight()

    def collect_all_vis(self, error=None, correct_class=0, activations=None):
        # if error == None:
        #     error = np.zeros(self.number_of_classes)
        #     error[correct_class] = 1.
        vis = np.zeros([28, 28])
        for output in range(self.number_of_classes):
            # vis += self.neurons['out{}'.format(output)].visualisation * error[output]
            vis += self.neurons['out{}'.format(output)].visualisation * activations['out{}'.format(output)]
        return vis

    def convert_vis_to_activations(self, neuron='', vis=None, norm=False):
        if neuron != '':
            vis = self.neurons[neuron].visualisation
        if norm and np.max(vis) != np.min(vis):
            vis = (vis - np.min(vis)) / (np.max(vis) - np.min(vis))
        activations = {}
        for y in range(28):
            for x in range(28):
                idx = (y * 28) + x
                activations['in{}'.format(idx)] = vis[y][x]
        return activations

    def remove_all_stored_values(self):
        deleted_neurons = []
        for neuron in self.neurons:
            if 'out' not in neuron:
                deleted_neurons.append(neuron)
        for del_n in deleted_neurons:
            self.delete_neuron(del_n)
        # for i in range(self.number_of_classes):
        #     self.neurons['out{}'.format(i)].synapses = {}

    def remove_hidden_neurons(self, connections):
        new_conn = {}
        for conn in connections:
            if 'in' in conn or 'p' in conn:
                new_conn[conn] = connections[conn]
        return new_conn

    def convert_net_and_clean(self):
        # self.procedural.append(create_network(self))
        # self.n_procedural_out += self.number_of_classes
        if len(self.procedural) >= 4:
            new_net, centroids = create_network(self, polar=True, correctness=False)
        else:
            new_net, centroids = create_network(self, polar=False, correctness=True)
        self.procedural.append(new_net)
        for layer in new_net:
            self.n_procedural_out += len(layer)
        # self.procedural = build_network(self, polar=True)
        # self.n_procedural_out = 0
        # for layer in self.procedural:
        #     self.n_procedural_out += len(layer)
        # self.number_of_inputs + len(self.procedural[-1])
        # for i in range(self.number_of_inputs):
        #     self.neuron_activity['in{}'.format(i)] = 0.
        self.remove_all_stored_values()
        return centroids

    def procedural_output(self, inputs):
        output = [0. for i in range(self.number_of_classes)]
        if len(self.procedural) == 0:
            return output, inputs[2:]
        all_out = []
        all_act = []
        for net in self.procedural:
            # pro_out, neuron_out = forward_propagate(self.procedural, inputs)
            # pro_out, neuron_out = forward_propagate(net, inputs)
            pro_out, neuron_out = forward_matrix_propagate(net, inputs)
            inputs = np.hstack([inputs, neuron_out])
            all_act = np.hstack([all_act, neuron_out])
            if len(all_out):
                all_out = np.vstack([all_out, pro_out])
            else:
                all_out = [pro_out]
        # for out, value in enumerate(pro_out):
        #     output[out] += value

        if len(self.procedural) >= 1:
            for out, value in enumerate(all_out[-1]):
                output[out] += value
        else:
            for net in all_out:
                for out, value in enumerate(net):
                    output[out] += value
        return output, all_act

    def error_driven_neuro_genesis(self, activations, output_error, weight_multiplier=1., label=-1,
                                   x=None, y=None):
        if np.max(np.abs(output_error)) > self.error_threshold:
            if self.replaying:
                # self.response(self.convert_vis_to_activations('out{}'.format(correct_class)), replay=True)
                self.response(self.convert_vis_to_activations(vis=self.collect_all_vis(error=output_error,
                                                                                       activations=activations)),
                              replay=True)
            activations = self.remove_output_neurons(activations)
            neuron_label = self.add_neuron(activations, x=x, y=y)
            self.neurons[neuron_label].output = label#(output_error * -1).argmax()
            # if len(self.correctness[label]):
            #     average_val = sum(self.correctness[label].values()) / \
            #                   len(self.correctness[label])
            #     self.correctness[label][neuron_label] = average_val
            #     self.neurons[neuron_label].correctness = average_val
            # else:
            # self.correctness[label][neuron_label] = 0.
            for output, error in enumerate(output_error):
                if abs(error) > self.error_threshold:
                    # self.current_importance += self.old_weight_modifier
                    # error *= self.current_importance
                    # self.age_output_synapses(reward=True)
                    self.neurons['out{}'.format(output)].add_connection(neuron_label,
                                                                        freq=1.,
                                                                        weight=-error * weight_multiplier,
                                                                        sensitivities=self.neuron_selectivity,
                                                                        # width=0.5,
                                                                        reward_decay=self.reward_decay)
                    self.synapse_count += 1
                    if self.replaying:
                        self.visualise_neuron('out{}'.format(output), only_pos=False)
                    self.neuron_connectedness[neuron_label] = 1
            return neuron_label
        else:
            return "thresholded"

    def pass_errors_to_outputs(self, errors, lr):
        for out, error in enumerate(errors):
            for synapse in self.neurons['out{}'.format(out)].synapses:
                for syn in self.neurons['out{}'.format(out)].synapses[synapse]:
                    weight_d = syn.activity * error * lr
                    syn.weight -= weight_d

    def consolidate(self):
        return "new connections to create neurons"

    def visualise_neuron(self, neuron, sensitive=False, only_pos=False):
        visualisation = np.zeros([28, 28])
        for pre in self.neurons[neuron].synapses:
            if 'in' in pre:
                idx = int(pre.replace('in', ''))
                x = idx % 28
                y = int((idx - x) / 28)
                for syn in self.neurons[neuron].synapses[pre]:
                    if sensitive:
                        visualisation[y][x] += syn.contribution()
                    else:
                        visualisation[y][x] += syn.freq
            elif 'out' not in pre:
                for syn in self.neurons[neuron].synapses[pre]:
                    if only_pos:
                        if syn.weight > 0.:
                            if sensitive:
                                visualisation += self.neurons[pre].visualisation * syn.contribution() * \
                                                 syn.weight / len(self.neurons[neuron].synapses) # not if multapse
                            else:
                                visualisation += self.neurons[pre].visualisation * syn.freq * \
                                                 syn.weight / len(self.neurons[neuron].synapses) # not if multapse
                    else:
                        if sensitive:
                            visualisation += self.neurons[pre].visualisation * syn.contribution() * \
                                             syn.weight / len(self.neurons[neuron].synapses) # not if multapse
                        else:
                            visualisation += self.neurons[pre].visualisation * syn.freq * \
                                             syn.weight / len(self.neurons[neuron].synapses) # not if multapse
        self.neurons[neuron].visualisation = visualisation
        return visualisation

    def visualise_mnist_output(self, output, contribution=True):
        visualisation = np.zeros([28, 28])
        output_neuron = self.neurons['out{}'.format(output)]
        for pre in self.neurons['out{}'.format(output)].synapses:
            if self.neurons['out{}'.format(output)].synapses[pre][0].weight > 0:
                for inputs in self.neurons[pre].synapses:
                    if 'in' in inputs:
                        idx = int(inputs.replace('in', ''))
                        x = idx % 28
                        y = int((idx - x) / 28)
                        for syn in self.neurons[pre].synapses[inputs]:
                            if contribution:
                                visualisation[y][x] += syn.contribution()
                            else:
                                visualisation[y][x] += syn.freq
        # plt.imshow(visualisation, cmap='hot', interpolation='nearest', aspect='auto')
        # plt.savefig("./plots/{}{}.png".format('mnist_memory', output), bbox_inches='tight', dpi=200)
        return visualisation

    def visualise_mnist_activations(self, activations):
        visualisation = np.zeros([28, 28])
        for inputs in activations:
            if 'in' in inputs:
                idx = int(inputs.replace('in', ''))
                x = idx % 28
                y = int((idx - x) / 28)
                visualisation[y][x] += activations[inputs]
        # plt.imshow(visualisation, cmap='hot', interpolation='nearest', aspect='auto')
        # plt.savefig("./plots/{}.png".format('mnist_activations_vis'), bbox_inches='tight', dpi=200)
        return visualisation







