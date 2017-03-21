'''
network.py - Network methods for dealing with UMIs
=========================================================

:Author: Tom Smith
:Release: $Id$
:Date: |today|
:Tags: Python UMI

'''
import collections
import itertools
import sys
import numpy as np

import pyximport
pyximport.install(build_in_temp=False)

try:
    from umi_tools._dedup_umi import edit_distance
    import umi_tools.Utilities as U

except:
    from _dedup_umi import edit_distance
    import Utilities as U

sys.setrecursionlimit(10000)


def breadth_first_search(node, adj_list):
    searched = set()
    found = set()
    queue = set()
    queue.update((node,))
    found.update((node,))

    while len(queue) > 0:
        node = (list(queue))[0]
        found.update(adj_list[node])
        queue.update(adj_list[node])
        searched.update((node,))
        queue.difference_update(searched)

    return found


def recursive_search(node, adj_list):
    children = adj_list[node]
    children = [x for x in children if x not in recursive_search.component]
    for child in children:
        recursive_search.component.update((child,))
        recursive_search.component.update(
            recursive_search(child, adj_list))
    return recursive_search.component


def breadth_first_search_recursive(node, adj_list):
    try:
        recursive_search.component = set((node,))
        return recursive_search(node, adj_list)

    except RecursionError as error:
        U.info('Recursion Error: %s' % error)
        return breadth_first_search(node, adj_list)


def remove_umis(adj_list, cluster, nodes):
    '''removes the specified nodes from the cluster and returns
    the remaining nodes '''

    # list incomprehension: for x in nodes: for node in adj_list[x]: yield node
    nodes_to_remove = set([node
                           for x in nodes
                           for node in adj_list[x]] + nodes)

    return cluster - nodes_to_remove


class UMIClusterer:
    '''A functor that clusters a dictionary of UMIs and their counts.
    The primary return value is either a list of representative UMIs
    or a list of lists where each inner list represents the contents of
    one cluster. 

    Optionally:

      - identify the parent UMIs and return:
         - selected reads
         - umis
         - counts

    The initiation of the functor defines the methods:

      ** get_adj_list ** - returns the edges connecting the UMIs

      ** connected_components ** - returns clusters of connected components
                                   using the edges in the adjacency list

      ** get_best ** - returns the parent UMI(s) in the connected_components

      ** reduce_clusters ** - loops through the connected components in a
                              cluster and returns the unique reads. Optionally
                              returns lists of umis and counts per umi also

    Note: The get_adj_list and connected_components methods are not required by
    all custering methods. Where there are not required, the methods return
    None or the input parameters.

    '''

    # "get_best" methods #

    def _get_best_min_account(self, cluster, adj_list, counts):
        ''' return the min UMI(s) need to account for cluster'''
        if len(cluster) == 1:
            return list(cluster)

        sorted_nodes = sorted(cluster, key=lambda x: counts[x],
                              reverse=True)

        for i in range(len(sorted_nodes) - 1):
            if len(remove_umis(adj_list, cluster, sorted_nodes[:i+1])) == 0:
                return sorted_nodes[:i+1]

    def _get_best_higher_counts(self, cluster, counts):
        ''' return the UMI with the highest counts'''
        if len(cluster) == 1:
            return list(cluster)[0]
        else:
            sorted_nodes = sorted(cluster, key=lambda x: counts[x],
                                  reverse=True)
            return sorted_nodes[0]

    def _get_best_percentile(self, cluster, counts):
        ''' return all UMIs with counts >1% of the
        median counts in the cluster '''

        if len(cluster) == 1:
            return list(cluster)
        else:
            threshold = np.median(list(counts.values()))/100
            return [read for read in cluster if counts[read] > threshold]

    def _get_best_null(self, cluster, counts):
        ''' return all UMIs in the cluster'''

        return list(cluster)

    # "get_adj_list" methods #

    def _get_adj_list_adjacency(self, umis, counts, threshold):
        ''' identify all umis within hamming distance threshold'''

        adj_list = {umi: [] for umi in umis}
        for umi1, umi2 in itertools.combinations(umis, 2):
            if edit_distance(umi1, umi2) <= threshold:
                adj_list[umi1].append(umi2)
                adj_list[umi2].append(umi1)

        return adj_list

    def _get_adj_list_directional(self, umis, counts, threshold=1):
        ''' identify all umis within the hamming distance threshold
        and where the counts of the first umi is > (2 * second umi counts)-1'''

        adj_list = {umi: [] for umi in umis}
        for umi1, umi2 in itertools.combinations(umis, 2):
            if edit_distance(umi1, umi2) <= threshold:
                if counts[umi1] >= (counts[umi2]*2)-1:
                    adj_list[umi1].append(umi2)
                if counts[umi2] >= (counts[umi1]*2)-1:
                    adj_list[umi2].append(umi1)

        return adj_list

    def _get_adj_list_null(self, umis, counts, threshold):
        ''' for methods which don't use a adjacency dictionary'''
        return None

    # "get_connected_components" methods #

    def _get_connected_components_adjacency(self, umis, graph, counts):
        ''' find the connected UMIs within an adjacency dictionary'''

        # TS: TO DO: Work out why recursive function does lead to same
        # final output. Then uncomment below

        #if len(graph) < 10000:
        #    self.search = breadth_first_search_recursive
        #else:
        #    self.search = breadth_first_search

        found = set()
        components = list()

        for node in sorted(graph, key=lambda x: counts[x], reverse=True):
            if node not in found:
                #component = self.search(node, graph)
                component = breadth_first_search(node, graph)
                found.update(component)
                components.append(component)

        return components

    def _get_connected_components_null(self, umis, adj_list, counts):
        ''' for methods which don't use a adjacency dictionary'''
        return umis

    # "group" methods #

    def _group_unique(self, clusters, adj_list, counts):
        ''' return groups for unique method'''
        if len(clusters) == 1:
            groups = [clusters]
        else:
            groups = [[x] for x in clusters]

        return groups

    def _group_directional(self, clusters, adj_list, counts):
        ''' return groups for directional method'''

        observed = set()
        groups = []

        for cluster in clusters:
            if len(cluster) == 1:
                groups.append(list(cluster))
                observed.update(cluster)
            else:
                cluster = sorted(cluster, key=lambda x: counts[x],
                                 reverse=True)
                # need to remove any node which has already been observed
                temp_cluster = []
                for node in cluster:
                    if node not in observed:
                        temp_cluster.append(node)
                        observed.add(node)
                groups.append(temp_cluster)

        return groups

    def _group_adjacency(self, clusters, adj_list, counts):
        ''' return groups for adjacency method'''

        groups = []

        for cluster in clusters:
            if len(cluster) == 1:
                groups.append(list(cluster))

            else:
                observed = set()

                lead_umis = self._get_best_min_account(cluster,
                                                       adj_list, counts)
                observed.update(lead_umis)

                for lead_umi in lead_umis:
                    connected_nodes = set(adj_list[lead_umi])
                    groups.append([lead_umi] +
                                  list(connected_nodes - observed))
                    observed.update(connected_nodes)

        return groups

    def _group_cluster(self, clusters, adj_list, counts):
        ''' return groups for cluster or directional methods'''

        groups = []
        for cluster in clusters:
            groups.append(sorted(cluster, key=lambda x: counts[x], reverse=True))

        return groups

    def _group_percentile(self, clusters, adj_list, counts):
        ''' Return "groups" for the the percentile method. Note
        that grouping isn't really compatible with the percentile
        method. This just returns the retained UMIs in a structure similar
        to other methods '''

        retained_umis = self.get_best(clusters, counts)
        groups = [[x] for x in retained_umis]

        return groups

    # "reduce_clusters" methods #

    def _reduce_clusters_multiple(self, clusters, adj_list, counts,
                                  stats=False):
        ''' collapse clusters down to the UMI(s) which account for the cluster
        using the adjacency dictionary and return the list of final UMIs'''

        # TS - the "adjacency" variant of this function requires an adjacency
        # list to identify the best umi, whereas the other variants don't
        # As temporary solution, pass adj_list to all variants
        final_umis = []
        umi_counts = []

        for cluster in clusters:
            parent_umis = self.get_best(cluster, adj_list, counts)
            final_umis.extend(parent_umis)

            if stats:
                umi_counts.extend([counts[umi] for umi in parent_umis])

        return final_umis, umi_counts

    def _reduce_clusters_single(self, clusters, adj_list,
                                counts, stats=False):
        ''' collapse clusters down to the UMI which accounts for the cluster
        using the adjacency dictionary and return the list of final UMIs'''

        final_umis = []
        umi_counts = []

        for cluster in clusters:
            parent_umi = self.get_best(cluster, counts)
            final_umis.append(parent_umi)

            if stats:
                umi_counts.append(sum([counts[x] for x in cluster]))

        return final_umis, umi_counts

    def _reduce_clusters_no_network(self, clusters, adj_list,
                                    counts, stats=False):
        ''' collapse down to the UMIs which accounts for the cluster
        and return the list of final UMIs'''

        final_umis = []
        umi_counts = []
        final_umis = self.get_best(clusters, counts)

        if stats:
            umi_counts.extend([counts[umi] for umi in final_umis])

        return final_umis

    def __init__(self, cluster_method="directional"):
        ''' select the required class methods for the cluster_method'''

        if cluster_method == "adjacency":
            self.get_adj_list = self._get_adj_list_adjacency
            self.get_connected_components = self._get_connected_components_adjacency
            self.get_best = self._get_best_min_account
            self.reduce_clusters = self._reduce_clusters_multiple
            self.get_groups = self._group_adjacency

        elif cluster_method == "directional":
            self.get_adj_list = self._get_adj_list_directional
            self.get_connected_components = self._get_connected_components_adjacency
            self.get_best = self._get_best_higher_counts
            self.reduce_clusters = self._reduce_clusters_single
            self.get_groups = self._group_directional

        elif cluster_method == "cluster":
            self.get_adj_list = self._get_adj_list_adjacency
            self.get_connected_components = self._get_connected_components_adjacency
            self.get_best = self._get_best_higher_counts
            self.reduce_clusters = self._reduce_clusters_single
            self.get_groups = self._group_cluster

        elif cluster_method == "percentile":
            self.get_adj_list = self._get_adj_list_null
            self.get_connected_components = self._get_connected_components_null
            self.get_best = self._get_best_percentile
            self.reduce_clusters = self._reduce_clusters_no_network
            # percentile method incompatible with defining UMI groups
            self.get_groups = self._group_percentile

        if cluster_method == "unique":
            self.get_adj_list = self._get_adj_list_null
            self.get_connected_components = self._get_connected_components_null
            self.get_best = self._get_best_null
            self.reduce_clusters = self._reduce_clusters_no_network
            self.get_groups = self._group_unique

    def __call__(self, umis, counts, threshold):
        '''Counts is a directionary that maps UMIs to their counts'''

        len_umis = [len(x) for x in umis]
        assert max(len_umis) == min(len_umis), (
            "not all umis are the same length(!):  %d - %d" % (
                min(len_umis), max(len_umis)))

        adj_list = self.get_adj_list(umis, counts, threshold)

        clusters = self.get_connected_components(umis, adj_list, counts)

        final_umis = [list(x) for x in
                      self.get_groups(clusters, adj_list, counts)]

        return final_umis


class ReadClusterer:
    '''This is a wrapper for applying the UMI methods to bundles of BAM reads.
    It is currently a pretty transparent wrapper on UMIClusterer. Basically
    taking a read bundle, extracting the UMIs and Counts, running UMIClusterer
    and returning the results along with annotated reads'''

    def __init__(self, cluster_method="directional"):
        
        self.UMIClusterer = UMIClusterer(cluster_method=cluster_method)

    def __call__(self, bundle, threshold, stats=False, further_stats=False,
                 deduplicate=True):

        umis = bundle.keys()

        counts = {umi: bundle[umi]["count"] for umi in umis}
        
        clusters = self.UMIClusterer(umis, counts, threshold)

        if deduplicate:
            final_umis = [cluster[0] for cluster in clusters]
            umi_counts = [sum(counts[umi] for umi in cluster)
                          for cluster in clusters]
            reads = [bundle[umi]["read"] for umi in final_umis]
        else:
            reads = bundle
            umi_counts = counts
            final_umis = clusters

        topologies = None
        nodes = None

        return (reads, final_umis, umi_counts, topologies, nodes)
