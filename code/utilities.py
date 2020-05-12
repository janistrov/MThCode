""" Various functions

Part of master thesis Segessenmann J. (2020)
"""
from typing import Dict, List, Any, Union

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import pandas as pd
from scipy.io import loadmat
from sklearn.preprocessing import MinMaxScaler
import time
import torch
import torch.nn as nn
import pickle
import os

import models


def train(params: dict):
    """ Trains model with parameters params.

        Saves:
            model.pth
            params.pkl
            eval_optim.pkl
    """
    # Load data
    X_train, X_test = data_loader(params=params)

    # Define model, criterion and optimizer
    model = models.FRNN(params)
    criterion = nn.MSELoss(reduction='none')
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

    # Training
    temp_loss = np.zeros([len(X_train), params['channel_size']])
    epoch_loss = np.zeros([params['epochs'], params['channel_size']])
    epoch_grad_norm = np.zeros(params['epochs'])
    temp_grad_norm = np.zeros(len(X_train))

    start_time = time.time()
    for epoch in range(params['epochs']):
        if epoch is not 0 and epoch % params['lr_decay'] is 0:
            for param_group in optimizer.param_groups:
                param_group['lr'] = param_group['lr'] / 2
        for T, X in enumerate(X_train):
            optimizer.zero_grad()
            prediction = model(X)
            loss = criterion(prediction, X[-1, :])
            temp_loss[T, :] = loss.detach()
            torch.autograd.backward(loss.mean())
            optimizer.step()
            for p in model.parameters():
                temp_grad_norm[T] = p.grad.data.norm(2).item()
        epoch_grad_norm[epoch] = np.mean(temp_grad_norm)
        epoch_loss[epoch, :] = np.mean(temp_loss, axis=0)
        print(f'Epoch: {epoch} | Loss: {np.mean(temp_loss):.4}')

    total_time = time.time() - start_time
    print(f'Time [min]: {total_time / 60:.3}')

    # Make optimizer evaluation dictionary
    eval_optimization = {'id': params['id'],
                         'loss': epoch_loss,
                         'grad_norm': epoch_grad_norm}

    # Save model
    directory = '../models/' + params['id']
    if not os.path.exists(directory):
        os.mkdir(directory)
    torch.save(model.state_dict(), directory + '/model.pth')
    pickle.dump(params, open(directory + '/params.pkl', 'wb'))
    pickle.dump(eval_optimization, open(directory + '/eval_optimization.pkl', 'wb'))


def make_prediction(id: str, train_set=False):
    """ Tests model an returns and saves distance metrics.

        Returns:
            eval_prediction

        Saves:
            eval_prediction.pkl
    """
    # Load parameters
    params = pickle.load(open('../models/' + id + '/params.pkl', 'rb'))

    # Load data
    X_train, X_test = data_loader(params=params)

    # Get trained model
    model = models.FRNN(params)
    model.load_state_dict(torch.load('../models/' + id + '/model.pth'))

    # Evaluate model
    model.eval()

    with torch.no_grad():
        test_pred = np.zeros((len(X_test), params['channel_size']))
        test_true = np.zeros((len(X_test), params['channel_size']))
        for T, X in enumerate(X_test):
            predictions = model(X)
            test_pred[T, :] = predictions.numpy()
            test_true[T, :] = X[-1, :].numpy()

        eval_prediction = {'id': id,
                           'test_pred': test_pred,
                           'test_true': test_true}
        if train_set is False:
            pickle.dump(eval_prediction, open('../models/' + id + '/eval_prediction.pkl', 'wb'))
            return eval_prediction
        else:
            train_pred = np.zeros((len(X_train), params['channel_size']))
            train_true = np.zeros((len(X_train), params['channel_size']))
            with torch.no_grad():
                for T, X in enumerate(X_train):
                    predictions = model(X)
                    train_pred[T, :] = predictions.numpy()
                    train_true[T, :] = X[-1, :].numpy()

    eval_prediction['train_pred'] = train_pred
    eval_prediction['train_true'] = train_true
    pickle.dump(eval_prediction, open('../models/' + id + '/eval_prediction.pkl', 'wb'))
    return eval_prediction


def make_distances(id: str, train_set=False):
    """ Computes Correlation, MSE, MAE for evaluation.

        Returns:
            eval_distances

        Saves:
            eval_distances.pkl
    """
    # Load parameters
    params = pickle.load(open('../models/' + id + '/params.pkl', 'rb'))
    eval_prediction = pickle.load(open('../models/' + id + '/eval_prediction.pkl', 'rb'))

    if train_set:
        pred = eval_prediction['train_pred']
        true = eval_prediction['train_true']
    else:
        pred = eval_prediction['test_pred']
        true = eval_prediction['test_true']

    # Calculate distances
    corr = []
    for i in range(params['channel_size']):
        corr.append(np.corrcoef(pred[:, i], true[:, i])[0, 1])
    mse = np.mean((pred - true) ** 2, axis=0)
    mae = np.mean(np.abs(pred - true), axis=0)

    eval_distances = {'ID': [id for i in range(params['channel_size'])],
                      'Node': [i for i in range(params['channel_size'])],
                      'Non-Linearity': [params['non-linearity'] for i in range(params['channel_size'])],
                      'Bias': [params['bias'] for i in range(params['channel_size'])],
                      'Recurrence': [params['lambda'] for i in range(params['channel_size'])],
                      'Correlation': corr,
                      'MSE': mse,
                      'MAE': mae}

    pickle.dump(eval_distances, open('../models/' + id + '/eval_distances.pkl', 'wb'))
    return eval_distances


def data_loader(id: str=None, params: dict=None, train_portion=0.8, windowing=True):
    """ Loads and prepares iEEG data for NN model.

        Returns:
            X_train, X_test
        Or (windowing=False):
            train_set, test_set
    """
    if params is None:
        params = pickle.load(open('../models/' + id + '/params.pkl', 'rb'))
    data_mat = loadmat(params['path2data'])
    data = data_mat['EEG'][:params['channel_size'], :params['sample_size']].transpose()

    # Normalization
    if params['normalization']:
        sc = MinMaxScaler(feature_range=(-1, 1))
        sc.fit(data)
        data = sc.transform(data)

    # To tensor
    data = torch.FloatTensor(data)

    # Split data into training and test set
    train_set = data[:int(train_portion * params['sample_size']), :]
    test_set = data[int(train_portion * params['sample_size']):, :]

    if windowing is False:
        return train_set, test_set

    # Windowing
    X_train, X_test = [], []
    for i in range(train_set.shape[0] - params['window_size']):
        X_train.append(train_set[i:i + params['window_size'], :])
    for i in range(test_set.shape[0] - params['window_size']):
        X_test.append(test_set[i:i + params['window_size'], :])

    return X_train, X_test


def plot_optimization(id: str):
    """ Makes and saves evaluation plots of optimization to ../figures/.

        Saves:
            Figure "optim_[...]"
    """
    eval_optimization = pickle.load(open('../models/' + id + '/eval_optimization.pkl', 'rb'))

    epochs = eval_optimization['loss'].shape[0]
    nodes = eval_optimization['loss'].shape[1]
    m = np.zeros((4, epochs*nodes))
    m[0, :] = np.repeat(np.arange(0, epochs), nodes)
    m[1, :] = np.tile(np.arange(0, nodes), epochs)
    m[2, :] = eval_optimization['loss'].reshape(1, -1)
    m[3, :] = np.repeat(eval_optimization['grad_norm'], nodes)

    df = pd.DataFrame(m.T, columns=['Epoch', 'Node', 'Loss', 'Grad norm'])
    df[['Epoch', 'Node']] = df[['Epoch', 'Node']].astype('int32')
    df['Node'] = df['Node'].astype('str')

    sns.set_style('darkgrid')
    fig = plt.figure(figsize=(10, 10))
    gs = fig.add_gridspec(nrows=2, ncols=2)
    ax = [[], [], []]
    ax[0] = fig.add_subplot(gs[:1, :1])
    ax[0] = sns.lineplot(x='Epoch', y='Loss', data=df)
    plt.xlim(0, epochs - 1)
    ax[1] = fig.add_subplot(gs[:1, 1:])
    ax[1] = sns.lineplot(x='Epoch', y='Grad norm', data=df)
    plt.xlim(0, epochs - 1)
    ax[2] = fig.add_subplot(gs[1:, :])
    ax[2] = sns.barplot(x='Node', y='Loss', data=df.where(df['Epoch'] == epochs - 1), color='tab:blue')
    plt.ylabel('Mean loss of last epoch')
    every_nth = 2
    for n, label in enumerate(ax[2].xaxis.get_ticklabels()):
        if n % every_nth != 0:
            label.set_visible(False)
    fig.savefig('../doc/figures/optim_' + eval_optimization['id'] + '.png')


def plot_weights(id: str, vmax=1, linewidth=.5, absolute=False):
    """ Makes and saves a heat map of weight matrix W to ../figures/.

        Saves:
            Figure "weights_[...]"
    """
    params = pickle.load(open('../models/' + id + '/params.pkl', 'rb'))
    # Get trained model
    model = models.FRNN(params)
    model.load_state_dict(torch.load('../models/' + id + '/model.pth'))
    W = model.W.weight.data.numpy()

    vmin = -vmax
    cmap = 'RdBu'
    ch = params['channel_size']
    hticklabels = np.arange(ch, W.shape[0], 1)

    if absolute:
        vmin = 0
        cmap = 'Blues'
        W = np.abs(W)

    fig = plt.figure(figsize=(10, 10))
    gs = fig.add_gridspec(nrows=W.shape[0], ncols=W.shape[0])
    cbar_ax = fig.add_axes([.925, .125, .02, .755])  # l,b,w,h

    ax0 = fig.add_subplot(gs[:ch, :ch])
    ax0.set_ylabel('to visible nodes')
    ax0.get_xaxis().set_visible(False)

    ax1 = fig.add_subplot(gs[:ch, ch:])
    ax1.get_xaxis().set_visible(False), ax1.get_yaxis().set_visible(False)
    ax1.set_ylabel('to hidden nodes')
    ax1.set_xlabel('from visible nodes')

    ax2 = fig.add_subplot(gs[ch:, :ch])
    ax2.set_ylabel('to hidden nodes')
    ax2.set_xlabel('from visible nodes')

    ax3 = fig.add_subplot(gs[ch:, ch:])
    ax3.get_yaxis().set_visible(False)
    ax3.set_xlabel('from hidden nodes')

    sns.heatmap(W[:ch, :ch], cmap=cmap, vmin=vmin, vmax=vmax, cbar=False, linewidths=linewidth, ax=ax0)
    sns.heatmap(W[:ch, ch:], cmap=cmap, vmin=vmin, vmax=vmax, cbar=False, linewidths=linewidth, ax=ax1)
    sns.heatmap(W[ch:, :ch], cmap=cmap, vmin=vmin, vmax=vmax, cbar=False, linewidths=linewidth, ax=ax2)
    sns.heatmap(W[ch:, ch:], cmap=cmap, vmin=vmin, vmax=vmax, cbar_ax=cbar_ax, linewidths=linewidth, ax=ax3)

    every_nth = int(W.shape[0]/40)
    for n, label in enumerate(ax2.yaxis.get_ticklabels()):
        if n % every_nth != 0:
            label.set_visible(False)

    fig.text(0.08, 0.65, 'to visible node', va='center', ha='center', rotation='vertical')
    fig.text(0.08, 0.27, 'to hidden node', va='center', ha='center', rotation='vertical')
    fig.text(0.35, 0.08, 'from visible node', va='center', ha='center')
    fig.text(0.77, 0.08, 'from hidden node', va='center', ha='center')
    fig.subplots_adjust(hspace=0.3, wspace=0.3)
    fig.savefig('../doc/figures/weights_' + id + '.png')


def plot_prediction(id: str, nodes_idx: list, lim_nr_samples=None, train_set=False, nodes2path=False):
    """ Makes and saves line plots of predictions to ../figures/.

        Saves:
            Figure "prediction_[...]"
    """
    # Get data
    eval_prediction = pickle.load(open('../models/' + id + '/eval_prediction.pkl', 'rb'))
    if train_set:
        if lim_nr_samples is None:
            lim_nr_samples = eval_prediction['train_pred'].shape[0]
        pred = eval_prediction['train_pred'][-lim_nr_samples:, nodes_idx]
        true = eval_prediction['train_true'][-lim_nr_samples:, nodes_idx]
    else:
        if lim_nr_samples is None:
            lim_nr_samples = eval_prediction['test_pred'].shape[0]
        pred = eval_prediction['test_pred'][-lim_nr_samples:, nodes_idx]
        true = eval_prediction['test_true'][-lim_nr_samples:, nodes_idx]

    # Make plot
    sns.set_style('darkgrid')
    ax = [[] for i in range(len(nodes_idx))]
    fig = plt.figure(figsize=(10, int(len(ax)) * 3))
    for i in range(len(ax)):
        ax[i] = fig.add_subplot(int(len(nodes_idx)), 1, i + 1)
        ax[i] = plt.plot(pred[:, i], color='tab:red', ls='--', label='Predicted values')
        ax[i] = plt.plot(true[:, i], color='tab:blue', label='True values')
        plt.ylabel('Magn. [-]')
        plt.xlabel('Time steps [Samples]')
        plt.title('Node ' + str(nodes_idx[i]))
        plt.xlim(left=0)
        plt.legend()
    plt.tight_layout()

    nodes_str = ''
    if nodes2path:
        for _, node in enumerate(nodes_idx):
            nodes_str = nodes_str + '_' + str(node)
    plt.savefig('../doc/figures/prediction_' + id + nodes_str + '.png')


def plot_multi_boxplots(eval_dists: pd.DataFrame, x: str, y: str, hue=None, ylim=None, save_name=None):
    """ Makes and saves box plots of results to ../figures/.

        Saves:
            Figure "boxplot_[...]"
    """
    plt.figure(figsize=(10, 8))
    sns.set_style('darkgrid')
    ax = sns.boxplot(x=x, y=y, data=eval_dists, hue=hue)
    ax.set(xlabel='', ylabel=y)
    sns.set_style('darkgrid')
    if ylim:
        plt.ylim(ylim[0], ylim[1])
    if save_name is None:
        save_name = x
    plt.savefig('../doc/figures/boxplots_' + save_name + '.png')


def plot_multi_scatter(titles: list, preds: list, trues: list, save_name='default'):
    """ Makes and saves scatter plots of predictions to ../figures/.

        Saves:
            Figure "scatter_[...]"
    """
    sns.set_style('darkgrid')
    ax = [[] for i in range(len(titles))]

    fig = plt.figure(figsize=(10, int(len(ax) / 2) * 5))
    for i in range(len(ax)):
        ax[i] = fig.add_subplot(int(len(ax)/2), 2, i + 1)
        ax[i] = plt.scatter(preds[i], trues[i], s=.01)
        ax[i] = plt.plot([-1, 1], [-1, 1], ls="--", color='red')
        plt.axis([-1, 1, -1, 1])
        plt.ylabel('Predicted value')
        plt.xlabel('True value')
        plt.title(titles[i])
    plt.tight_layout()
    plt.savefig('../doc/figures/scatter_' + save_name + '.png')


def plot_corr_map(id: str, size_of_samples=2000, save_name='default'):
    """ Makes and saves heat map of electrode correlation in train set to ../figures/.

        Saves:
            Figure "corr_[...]"
    """
    train_set, test_set = data_loader(id, windowing=False)

    df = pd.DataFrame(train_set[:size_of_samples, :].numpy())
    corr = df.corr()

    fig, ax = plt.subplots()
    plt.title('Node correlation over 2000 samples')
    sns.heatmap(corr, cmap='RdBu', vmin=-1, vmax=1, square=True)
    fig.savefig('../doc/figures/corr_' + save_name + '.png')


def print_params(id: str):
    params = pickle.load(open('../models/' + id + '/params.pkl', 'rb'))
    for keys, values in params.items():
        print(f'{keys}: {values}')
