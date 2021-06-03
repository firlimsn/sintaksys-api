# -*- coding: utf-8 -*-
"""Load Model.ipynb
code by Machine Learning team (Nur Sekti & Amilla)
Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1YjPpOZLnY0mV9c1cLrNOuftkbPzZW6gS
"""
#requirements
#!pip install docx2txt
#!pip install tensorflow==2.5.0

import re
import os

#import sys
#print(sys.path)

import numpy as np
import docx2txt

from keras.models import Model, load_model
from keras.layers import Input

#from model import truncated_acc, truncated_loss

np.random.seed(1234)

SOS = '\t' # start of sequence.
EOS = '*' # end of sequence.
CHARS = list('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ')
REMOVE_CHARS = '[#$%"\+@<=>!&,-.?:;()*\[\]^_`{|}~/\d\t\n\r\x0b\x0c]'

class CharacterTable(object):
    """Given a set of characters:
    + Encode them to a one-hot integer representation
    + Decode the one-hot integer representation to their character output
    + Decode a vector of probabilities to their character output
    """
    def __init__(self, chars):
        """Initialize character table.
        # Arguments
          chars: Characters that can appear in the input.
        """
        self.chars = sorted(set(chars))
        self.char2index = dict((c, i) for i, c in enumerate(self.chars))
        self.index2char = dict((i, c) for i, c in enumerate(self.chars))
        self.size = len(self.chars)
    
    def encode(self, C, nb_rows):
        """One-hot encode given string C.
        # Arguments
          C: string, to be encoded.
          nb_rows: Number of rows in the returned one-hot encoding. This is
          used to keep the # of rows for each data the same via padding.
        """
        x = np.zeros((nb_rows, len(self.chars)), dtype=np.float32)
        for i, c in enumerate(C):
            x[i, self.char2index[c]] = 1.0
        return x

    def decode(self, x, calc_argmax=True):
        """Decode the given vector or 2D array to their character output.
        # Arguments
          x: A vector or 2D array of probabilities or one-hot encodings,
          or a vector of character indices (used with `calc_argmax=False`).
          calc_argmax: Whether to find the character index with maximum
          probability, defaults to `True`.
        """
        if calc_argmax:
            indices = x.argmax(axis=-1)
        else:
            indices = x
        chars = ''.join(self.index2char[ind] for ind in indices)
        return indices, chars

    def sample_multinomial(self, preds, temperature=1.0):
        """Sample index and character output from `preds`,
        an array of softmax probabilities with shape (1, 1, nb_chars).
        """
        # Reshaped to 1D array of shape (nb_chars,).
        preds = np.reshape(preds, len(self.chars)).astype(np.float64)
        preds = np.log(preds) / temperature
        exp_preds = np.exp(preds)
        preds = exp_preds / np.sum(exp_preds)
        probs = np.random.multinomial(1, preds, 1)
        index = np.argmax(probs)
        char  = self.index2char[index]
        return index, char

def read_text(data_path, list_of_books):
    #text = ''
    for book in list_of_books:
        file_path = os.path.join(data_path, book)
        text = docx2txt.process(file_path)
        '''
        strings = file.read()
        text += strings + ' '
        '''
    return text

def tokenize(text):
    tokens = [re.sub(REMOVE_CHARS, '', token)
              for token in re.split("[-\n ]", text)]
    return tokens

def add_spelling_errors(token, error_rate): #Simulate some error mistakes
  assert(0.0 <= error_rate < 1.0)
  if len(token) < 3:
      return token
  rand = np.random.rand()
  # Here are 4 different ways spelling mistakes can occur,
  # each of which has equal chance.
  prob = error_rate / 4.0
  if rand < prob:
    # Replace a character with a random character.
    random_char_index = np.random.randint(len(token))
    token = token[:random_char_index] + np.random.choice(CHARS) \
            + token[random_char_index + 1:]
  elif prob < rand < prob * 2:
    # Delete a character.
    random_char_index = np.random.randint(len(token))
    token = token[:random_char_index] + token[random_char_index + 1:]
  elif prob * 2 < rand < prob * 3:
    # Add a random character.
    random_char_index = np.random.randint(len(token))
    token = token[:random_char_index] + np.random.choice(CHARS) \
            + token[random_char_index:]
  elif prob * 3 < rand < prob * 4:
    # Transpose 2 characters.
    random_char_index = np.random.randint(len(token) - 1)
    token = token[:random_char_index]  + token[random_char_index + 1] \
            + token[random_char_index] + token[random_char_index + 2:]
  else:
    # No spelling errors.
    pass
  return token
  
def transform(tokens, maxlen, error_rate=0.2, shuffle=True):
    """Transform tokens into model inputs and targets.
    All inputs and targets are padded to maxlen with EOS character.
    """
    if shuffle:
        print('Shuffling data.')
        np.random.shuffle(tokens)
    encoder_tokens = []
    decoder_tokens = []
    target_tokens = []
    for token in tokens:
        encoder = add_spelling_errors(token, error_rate=error_rate)
        encoder += EOS * (maxlen - len(encoder)) # Padded to maxlen.
        encoder_tokens.append(encoder)
    
        decoder = SOS + token
        decoder += EOS * (maxlen - len(decoder))
        decoder_tokens.append(decoder)
    
        target = decoder[1:]
        target += EOS * (maxlen - len(target))
        target_tokens.append(target)
        
        assert(len(encoder) == len(decoder) == len(target))
    return encoder_tokens, decoder_tokens, target_tokens

def batch(tokens, maxlen, ctable, batch_size=128, reverse=False):
    """Split data into chunks of `batch_size` examples."""
    def generate(tokens, reverse):
        while(True): # This flag yields an infinite generator.
            for token in tokens:
                if reverse:
                    token = token[::-1]
                yield token
    
    token_iterator = generate(tokens, reverse)
    data_batch = np.zeros((batch_size, maxlen, ctable.size),
                          dtype=np.float32)
    while(True):
        for i in range(batch_size):
            token = next(token_iterator)
            data_batch[i] = ctable.encode(token, maxlen)
        yield data_batch

def decode_sequences(inputs, input_ctable, target_ctable,
                     maxlen, reverse, encoder_model, decoder_model,
                     nb_examples, sample_mode='argmax', random=True):
    input_tokens = []
    
    if random:
        indices = np.random.randint(0, len(inputs), nb_examples)
    else:
        indices = range(nb_examples)
        
    for index in indices:
        input_tokens.append(inputs[index])

    input_sequences = batch(input_tokens, maxlen, input_ctable,
                            nb_examples, reverse)
    input_sequences = next(input_sequences)
    
    # Procedure for inference mode (sampling):
    # 1) Encode input and retrieve initial decoder state.
    # 2) Run one step of decoder with this initial state
    #    and a start-of-sequence character as target.
    #    Output will be the next target character.
    # 3) Repeat with the current target character and current states.

    # Encode the input as state vectors.    
    states_value = encoder_model.predict(input_sequences)
    
    # Create batch of empty target sequences of length 1 character.
    target_sequences = np.zeros((nb_examples, 1, target_ctable.size))
    # Populate the first element of target sequence
    # with the start-of-sequence character.
    target_sequences[:, 0, target_ctable.char2index[SOS]] = 1.0

    # Sampling loop for a batch of sequences.
    # Exit condition: either hit max character limit
    # or encounter end-of-sequence character.
    decoded_tokens = [''] * nb_examples
    for _ in range(maxlen):
        # `char_probs` has shape
        # (nb_examples, 1, nb_target_chars)
        char_probs, h, c = decoder_model.predict(
            [target_sequences] + states_value)

        # Reset the target sequences.
        target_sequences = np.zeros((nb_examples, 1, target_ctable.size))

        # Sample next character using argmax or multinomial mode.
        sampled_chars = []
        for i in range(nb_examples):
            if sample_mode == 'argmax':
                next_index, next_char = target_ctable.decode(
                    char_probs[i], calc_argmax=True)
            elif sample_mode == 'multinomial':
                next_index, next_char = target_ctable.sample_multinomial(
                    char_probs[i], temperature=0.5)
            else:
                raise Exception(
                    "`sample_mode` accepts `argmax` or `multinomial`.")
            decoded_tokens[i] += next_char
            sampled_chars.append(next_char) 
            # Update target sequence with index of next character.
            target_sequences[i, 0, next_index] = 1.0

        stop_char = set(sampled_chars)
        if len(stop_char) == 1 and stop_char.pop() == EOS:
            break
            
        # Update states.
        states_value = [h, c]
    
    # Sampling finished.
    input_tokens   = [re.sub('[%s]' % EOS, '', token)
                      for token in input_tokens]
    decoded_tokens = [re.sub('[%s]' % EOS, '', token)
                      for token in decoded_tokens]
    return input_tokens, decoded_tokens


def restore_model(path_to_full_model, hidden_size):
    """Restore model to construct the encoder and decoder."""
    model = load_model(path_to_full_model)
    encoder_inputs = model.input[0] # encoder_data
    encoder_lstm1 = model.get_layer('encoder_lstm_1')
    encoder_lstm2 = model.get_layer('encoder_lstm_2')
    
    encoder_outputs = encoder_lstm1(encoder_inputs)
    _, state_h, state_c = encoder_lstm2(encoder_outputs)
    encoder_states = [state_h, state_c]
    encoder_model = Model(inputs=encoder_inputs, outputs=encoder_states)

    decoder_inputs = model.input[1] # decoder_data
    decoder_state_input_h = Input(shape=(hidden_size,))
    decoder_state_input_c = Input(shape=(hidden_size,))
    decoder_states_inputs = [decoder_state_input_h, decoder_state_input_c]
    decoder_lstm = model.get_layer('decoder_lstm')
    decoder_outputs, state_h, state_c = decoder_lstm(
        decoder_inputs, initial_state=decoder_states_inputs)
    decoder_states = [state_h, state_c]
    decoder_softmax = model.get_layer('decoder_softmax')
    decoder_outputs = decoder_softmax(decoder_outputs)
    decoder_model = Model(inputs=[decoder_inputs] + decoder_states_inputs,
                          outputs=[decoder_outputs] + decoder_states)
    return encoder_model, decoder_model

import os
os.environ['CUDA_VISIBLE_DEVICES'] = '0'

'''
from utils import CharacterTable, transform
from utils import restore_model, decode_sequences
from utils import read_text, tokenize
'''

error_rate = 0.8
reverse = True
model_path = './model/seq2seq_epoch_10.h5'
hidden_size = 128
sample_mode = 'argmax'
data_path = './ref/'
ref = ['ref.docx']
uji = ['uji.docx']

#test_sentence = 'Aku suka bermain sepak bola. Ketidakpatuhan pasien terhadap diet dan terapi yang diberikan oleh dokter. Faktor lain yang dapat memengaruhi buruknya kontrol glikemik pada pasien DMT2 adalah riwayat keluarga, durasi menderita DMT2, komplikasi, aktivitas fisik yang kurang, dan rendahnya tingkat pendidikan. Sebagian besar subyek memiliki status gizi lebih yaitu overweight (24,61%) dan obesitas (52,31%). Status gizi lebih terutama obesitas lebih sering pada pasien DMT2 karena merupakan faktor risiko terpenting DMT2.'

def load(kalimat):
    text  = read_text(data_path, ref)
    vocab = tokenize(text)
    vocab = list(filter(None, set(vocab)))
    # `maxlen` is the length of the longest word in the vocabulary
    # plus two SOS and EOS characters.
    maxlen = max([len(token) for token in vocab]) + 2
    train_encoder, train_decoder, train_target = transform(
        vocab, maxlen, error_rate=error_rate, shuffle=False)
  
    misspelled_tokens = []
    # Uncomment or file reading
    # sentence = read_text(data_path, uji)
    # tokens = tokenize(test_sentence)
    sentence = kalimat
    tokens = tokenize(sentence)
    tokens = list(filter(None, tokens))
    nb_tokens = len(tokens)
    for token in tokens:
      token += EOS * (maxlen - len(token))
      misspelled_tokens.append(token)

    input_chars = set(' '.join(train_encoder))
    target_chars = set(' '.join(train_decoder))
    input_ctable = CharacterTable(input_chars)
    target_ctable = CharacterTable(target_chars)
    
    encoder_model, decoder_model = restore_model(model_path, hidden_size)
    
    input_tokens, decoded_tokens = decode_sequences(
        misspelled_tokens, input_ctable, target_ctable,
        maxlen, reverse, encoder_model, decoder_model, nb_tokens,
        sample_mode=sample_mode, random=False)
    
    #print('', ' '.join([token for token in decoded_tokens]))
    result = ' '.join([token for token in decoded_tokens])
    return result