#!/usr/bin/env python

import sys
import warnings

import click
import igraph as ig
import numpy as np
import pandas as pd

from metgem.config import RADIUS
from metgem.utils.network import Network, generate_id
from metgem.workers.core import (ReadDataWorker, ComputeScoresWorker,
                                 ForceDirectedGraphWorker, ForceDirectedWorker, MaxConnectedComponentsWorker,
                                 TSNEWorker, SaveProjectWorker)
from metgem.workers.options import (ScoreComputationOptions, ForceDirectedVisualizationOptions,
                                    TSNEVisualizationOptions)


class Project(object):
    def __init__(self, fname: str, network: Network):
        self.fname = fname
        self.network = network
        self.layouts = {}
        self.graphs = {}


@click.group(chain=True, invoke_without_command=True)
@click.option('-i', '--input', required=True, help='Input file to process')
@click.option('-o', '--output', default='output.npz', help='Output filename')
@click.option('--ms1-data/--ms2-data', default=False, is_flag=True,
              help="Use this option if the precursor ion's mass is unknown. Only fragments will be compared.")
@click.option('--min-intensity', type=int, default=0,
              help="Filter out peaks with relative intensity below this percentage of highest intense peak")
@click.option('--parent-filter-tolerance', type=int, default=17, help='in Da')
@click.option('--min-matched-peaks-search', type=int, default=6,
              help="Window rank filter's parameters: for each peak in the spectrum, "
                   "it is kept only if it is in top `min_matched_peaks_search` in the +/- `matched_peaks_window` window")
@click.option('--matched-peaks-window', type=int, default=50, help='in Da')
@click.option('--min-matched-peaks', type=int, default=4,
              help='Minimum number of common peaks between two spectra')
@click.option('-t', '--mz-tolerance', type=float, default=0.02,
              help='Maximum difference (in Da) between two ions masses to consider they correspond to the same ion.')
@click.pass_context
def cli(ctx, input, output, ms1_data, min_intensity, parent_filter_tolerance,
        min_matched_peaks_search, matched_peaks_window,
        min_matched_peaks, mz_tolerance):

    options = {}
    interactions = pd.DataFrame()

    # +-----------+
    # | Read Data |
    # +-----------+
    use_min_intensity_filter = min_intensity != 0
    use_parent_filter = parent_filter_tolerance != 0
    use_window_rank_filter = min_matched_peaks_search != 0 and min_matched_peaks_search != 0
    use_filtering = use_min_intensity_filter or use_parent_filter or use_window_rank_filter

    options['score'] = ScoreComputationOptions()
    options['score'].update({
        'mz_tolerance': mz_tolerance,
        'min_intensity': min_intensity,
        'parent_filter_tolerance': parent_filter_tolerance,
        'min_matched_peaks': min_matched_peaks,
        'min_matched_peaks_search': min_matched_peaks_search,
        'matched_peaks_window': matched_peaks_window,
        'is_ms1_data': ms1_data,
        'use_filtering': use_filtering,
        'use_min_intensity_filter': use_min_intensity_filter,
        'use_parent_filter': use_parent_filter,
        'use_window_rank_filter': use_window_rank_filter})
    worker = ReadDataWorker(input, options['score'])
    try:
        mzs, spectra = worker.run()
    except NotImplementedError:
        print('Unknown file format.')
        sys.exit(1)

    # +---------------------------+
    # | Compute Similarity Matrix |
    # +---------------------------+
    worker = ComputeScoresWorker(mzs, spectra, options['score'])
    with click.progressbar(length=worker.max, label='Computing scores') as pbar:
        worker.updated.connect(lambda v: pbar.update(pbar.pos + v))
        scores = worker.run()

    network = Network()
    network.mzs = mzs
    network.spectra = spectra
    network.scores = scores
    network.options = options
    network.interactions = interactions

    ctx.obj = Project(fname=output, network=network)


# noinspection PyUnusedLocal
@cli.result_callback()
@click.pass_obj
def save_project(project, *args, **kwargs):
    worker = SaveProjectWorker(project.fname, project.network, None, project.network.options,
                               project.layouts, project.graphs)
    worker.run()


@cli.command('+network')
@click.option('--top-k', type=int, default=10, help='Maximum numbers of edges for each nodes in the network')
@click.option('--pairs-min-cosine', type=float, default=0.7,
              help='Minimum cosine score for network generation.')
@click.option('--max-connected-nodes', type=int, default=1000,
              help='Maximum size of a Force Directed cluster.')
@click.pass_obj
def add_network(project, **opts):
    add_network.counter += 1
    id_ = generate_id(ForceDirectedVisualizationOptions.name)

    graph = ig.Graph()
    nodes_idx = np.arange(project.network.scores.shape[0])
    graph.add_vertices(nodes_idx.tolist())

    radii = np.asarray([RADIUS for _ in nodes_idx])

    project.network.options[id_] = ForceDirectedVisualizationOptions()
    project.network.options[id_].update(opts)

    graph_worker = ForceDirectedGraphWorker(project.network.scores, project.network.mzs, graph,
                                            project.network.options[id_])
    max_cc_worker = MaxConnectedComponentsWorker(graph, project.network.options[id_])\
        if opts['max_connected_nodes'] > 0 else None

    fd_worker = ForceDirectedWorker(graph, radii)

    with click.progressbar(length=graph_worker.max + fd_worker.max,
                           label=f'Generating Network {add_network.counter}') as pbar:
        graph_worker.updated.connect(pbar.update)
        interactions, graph = graph_worker.run()

        if max_cc_worker is not None:
            graph = max_cc_worker.run()

        fd_worker.updated.connect(lambda v: pbar.update(graph_worker.max + v - pbar.pos))
        layout, isolated_nodes = fd_worker.run()

    project.graphs[id_] = {'graph': graph,
                           'interactions': interactions}
    project.layouts[id_] = {'layout': layout,
                            'isolated_nodes': isolated_nodes,
                            'radii': radii}


add_network.counter = 0


@cli.command('+tsne')
@click.option('--perplexity', type=int, default=6, help='Perplexity.')
@click.option('--learning-rate', type=int, default=200, help='Learning Rate.')
@click.option('--early-exaggeration', type=int, default=12, help='Early exaggeration.')
@click.option('--barnes-hut/--exact', default=False, help='Enable Barnes-Hut Approximation.')
@click.option('--angle', type=float, default=0.5,
              help="Angle used for Barnes-Hut Approximation. Not very sensitive to changes in the range 0.2 - 0.8. "
                   "Angle less than 0.2 has quickly increasing computation time and angle greater 0.8 has quickly "
                   "increasing error.",)
@click.option('--n-iter', type=int, default=1000, help='Maximum Number of Iterations.')
@click.option('--min-score', type=float, default=0.7,
              help="Filter out nodes that don't have more than a fixed number neighbors above the threshold.")
@click.option('--min-scores-above-threshold', type=int, default=1,
              help="Filter out nodes that don't have more than a fixed number neighbors above the threshold.")
@click.option('--random', default=False, help="Use Random Initialization.")
@click.pass_obj
def add_tsne(project, **opts):
    add_tsne.counter += 1
    id_ = generate_id(TSNEVisualizationOptions.name)

    radii = np.asarray([RADIUS for _ in range(project.network.scores.shape[0])])

    project.network.options[id_] = TSNEVisualizationOptions()
    project.network.options[id_].update(opts)

    worker = TSNEWorker(project.network.scores, project.network.options[id_])
    with click.progressbar(length=worker.max,
                           label=f'Generating t-SNE {add_tsne.counter}') as pbar:
        worker.updated.connect(pbar.update)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            layout, isolated_nodes = worker.run()
    project.layouts[id_] = {'layout': layout,
                            'isolated_nodes': isolated_nodes,
                            'radii': radii}


add_tsne.counter = 0


if __name__ == '__main__':
    cli()
