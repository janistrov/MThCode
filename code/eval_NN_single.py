""" Basic evaluation of one single NN

Part of master thesis Segessenmann J. (2020)
"""
import utilities as util
import models
import pandas as pd
import torch
import pickle
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

id = 'test_2'
util.print_params(id)

util.plot_optimization(id)

util.make_prediction(id)

df = pd.DataFrame(util.make_distances(id))
print('---------')
print('Mean Corr.: ' + str(df['Correlation'].mean()))
print('Mean MSE.: ' + str(df['MSE'].mean()))
print('Mean MAE.: ' + str(df['MAE'].mean()))

util.plot_prediction(id, [5, 26, 46, 54])

util.plot_weights(id, linewidth=0)


