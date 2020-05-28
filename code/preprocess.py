import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import pandas as pd
from scipy.io import loadmat
from scipy.signal import hilbert
from scipy.signal import savgol_filter
from scipy import fftpack
from sklearn.preprocessing import MinMaxScaler
import time
import torch
import torch.nn as nn
import pickle
from os import path
from pandas.plotting import autocorrelation_plot
from scipy import signal
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from scipy.stats.kde import gaussian_kde
from matplotlib.ticker import MaxNLocator

import utilities as util
import models


def node_reduction(data: np.ndarray, n_clusters: int, max_n_clusters=20, n_components=12, sample_labels=None):
    """ Reduces node dimension to n_clusters.

    :param data: Data of size (n_samples, n_nodes)
    :param n_clusters: Number of clusters
    :param max_n_clusters: Maximum number of clusters for evaluation
    :param n_components: Number of PCA components
    :return: df: DataFrame
    """
    n_samples = data.shape[0]
    n_nodes = data.shape[1]

    # Perform PCA for dimensionality reduction
    pca = PCA(n_components=n_components)
    pca_result = pca.fit_transform(data.T)

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(pca_result[:, 0], pca_result[:, 1], c=pca_result[:, 2])
    ax.set_xlabel('1st principal component')
    ax.set_ylabel('2nd principal component')
    ax.set_title('First 3 principal components')
    plt.tight_layout()
    fig.savefig('../doc/figures/preprocess_pca.png')

    # Check score of K-Means for max_n_clusters
    n_clusters_list = list(range(1, max_n_clusters + 1))
    score = []
    for i, val in enumerate(n_clusters_list):
        km = KMeans(n_clusters=val)
        clusters = km.fit(pca_result)
        score.append(clusters.inertia_ / n_nodes)

    fig = plt.figure(figsize=(5, 5))
    ax = fig.gca()
    plt.plot(n_clusters_list, score)
    plt.xlabel('Number of clusters')
    plt.ylabel('Mean squared distance')
    plt.title('Distance to nearest cluster center')
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    plt.tight_layout()
    fig.savefig('../doc/figures/preprocess_kmeans_n_clusters.png')

    # Perform K-Means on data
    km = KMeans(n_clusters=n_clusters)
    clusters = km.fit(pca_result)

    df = pd.DataFrame(pca_result)
    df['Cluster'] = clusters.labels_
    fig = plt.figure(figsize=(5, 5))
    sns.scatterplot(x=0, y=1, data=df, s=50, hue='Cluster', style='Cluster', palette='colorblind')
    plt.xlabel('1st principal component')
    plt.ylabel('2nd principal component')
    plt.title('Clustering of the first two princ. components')
    plt.tight_layout()
    fig.savefig('../doc/figures/preprocess_kmeans_result.png')

    # Make DataFrame
    df = pd.DataFrame()
    df['sample'] = np.tile(np.arange(0, n_samples), n_nodes)
    df['node'] = np.repeat(np.arange(0, n_nodes), n_samples)
    df['cluster'] = np.repeat(list(clusters.labels_), n_samples)
    df['value'] = data.T.flatten()
    if sample_labels is not None:
        df['sample_label'] = np.tile(sample_labels, n_nodes)

    return df


def acf(data: np.ndarray, n_lags, partial=False):
    """ Auto Correlation Function.

    :param data: Array of size (n_samples, n_nodes)
    :param n_lags: Lag size [samples]
    :param partial: Choose for partial or non-partial
    :return:
    """
    n_samples = data.shape[0]
    n_nodes = data.shape[1]

    lags = [i for i in range(n_lags)]
    acf_list = []

    if partial:
        for i in range(n_nodes):
            corr = [1. if lag == 0 else np.corrcoef(data[lag:, i], data[:-lag, i])[0][1] for lag in lags]
            acf_list.append(np.array(corr))
            acf_array = np.array(acf_list).T
    else:
        for i in range(n_nodes):
            mean = np.mean(data[:, i])
            var = np.var(data[:, i])
            data_p = data[:, i] - mean
            corr = [1. if lag == 0 else np.sum(data_p[lag:] * data_p[:-lag]) / n_samples / var for lag in lags]
            acf_list.append(np.array(corr))
            acf_array = np.array(acf_list).T

    # Confidence
    conf = (1.96/np.sqrt(n_samples), -1.96/np.sqrt(n_samples))

    return acf_array, conf


def fft(data: np.ndarray, fs: float, downscale_factor=None):
    """

    :param data:
    :param fs:
    :param downscale_factor:
    :return:
    """
    n_samples = data.shape[0]
    n_nodes = data.shape[1]

    spect = np.zeros((n_samples, n_nodes))
    for i in range(n_nodes):
        spect[:, i] = np.abs(fftpack.fft(data[:, i]))
    freq = fftpack.fftfreq(n_samples) * fs

    # Cut negative frequencies
    spect_pos = spect[:len(freq[freq >= 0])]
    freq_pos = freq[freq >= 0]

    if downscale_factor is not None:
        spect_resampled = []
        for i in range(n_nodes):
            spect_filtered = savgol_filter(np.abs(spect_pos[:, i]), int(n_samples/200)-1, 3)
            spect_resampled.append(signal.resample_poly(spect_filtered, up=3, down=3*downscale_factor))
        freq_resampled = signal.resample_poly(freq_pos, up=3, down=3*downscale_factor)

        return np.array(spect_resampled).T, freq_resampled

    return spect_pos, freq_pos


def distribution(data: np.ndarray, xlim: tuple=None):
    """

    :param data:
    :param xlim:
    :return:
    """
    n_nodes = data.shape[1]

    if xlim is None:
        xlim = (np.min(data), np.max(data))
    kde_x = np.linspace(xlim[0], xlim[1], 500)
    density = []
    for i in range(n_nodes):
        kde = gaussian_kde(data[:, i])
        density.append(kde(kde_x))

    return kde_x, np.array(density).T


def plot_distribution(data: np.ndarray, xlim: tuple=None, n_clusters: int=6):
    """

    :param data:
    :param xlim:
    :param n_clusters:
    :return:
    """
    kde_x, kde = distribution(data, xlim=xlim)

    normal = np.sort(np.random.normal(size=data.shape[0]))
    df_qq = node_reduction(np.sort(data, axis=0), n_clusters=n_clusters, sample_labels=normal)

    df_kde = node_reduction(kde, n_clusters=n_clusters, sample_labels=kde_x)

    sns.set_style('whitegrid')
    fig = plt.figure(figsize=(8, 16))
    gs = fig.add_gridspec(nrows=int(n_clusters / 2 + 1), ncols=2)
    ax = [[] for i in range(n_clusters)]
    ax[0] = fig.add_subplot(gs[:1, :])
    sns.lineplot(x='sample_label', y='value', data=df_kde, hue='cluster', palette='colorblind', ax=ax[0])
    ax[0].set_xlabel('Magnitude')
    ax[0].set_ylabel('Density')

    color_list = sns.color_palette('colorblind', n_clusters)
    row = np.repeat(np.arange(1, int(n_clusters / 2 + 2)), 2)
    col = np.tile(np.array([[0, 1], [1, 2]]), 3)
    for i in range(n_clusters):
        ax[i] = fig.add_subplot(gs[row[i]:row[i + 2], col[0, i]:col[1, i]])
        for k in range(df_qq.shape[0]):
            if df_qq['cluster'][k] == i:
                node = df_qq['node'][k]
                break
        sns.scatterplot(x='sample_label', y='value', data=df_qq.where(df_qq['node'] == node),
                        ax=ax[i], label='from cluster ' + str(i), edgecolor=None, color=color_list[i])
        ax[i].set_xlabel('Theoretical quantiles')
        ax[i].set_ylabel('Sample quantiles')
        ax[i].legend()
    plt.tight_layout()
    plt.savefig('../doc/figures/preprocess_distribution.png')


def acf_plot(data: np.ndarray, n_clusters=5, n_lags=1000):
    """

    :param data:
    :param n_clusters:
    :param n_lags:
    :return:
    """
    acf, conf = acf(data, n_lags=n_lags)
    df = node_reduction(acf, n_clusters)
    plt.figure(figsize=(12, 8))
    sns.set_style('whitegrid')
    plt.plot([0, n_lags], [conf[1], conf[1]], color='black', ls='--')
    plt.plot([0, n_lags], [conf[0], conf[0]], color='black', ls='--')
    plt.xlim(0, n_lags)
    sns.lineplot(x='sample', y='value', data=df, hue='cluster', palette='colorblind')
    plt.xlabel('Lag')
    plt.ylabel('Correlation')
    plt.title('Autocorrelation')
    plt.savefig('../doc/figures/preprocess_acf.png')
