import networkx as nx
from panaroo.cdhit import *
from panaroo.merge_nodes import merge_nodes
from collections import defaultdict
from panaroo.cdhit import is_valid
from itertools import chain, combinations
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components


# Genes at the end of contigs are more likely to be false positives thus
# we can remove those with low support
def trim_low_support_trailing_ends(G, min_support=3, max_recursive=2):

    # fix trailing
    for i in range(max_recursive):
        bad_nodes = []
        removed = False
        for (node, val) in G.degree():
            if val <= 1:  # trailing node
                if G.node[node]['size'] < min_support:
                    bad_nodes.append(node)
        for node in bad_nodes:
            G.remove_node(node)
            removed = True

        if not removed: break

    return G

def collapse_families(G,
                      outdir,
                      family_threshold=0.7,
                      dna_error_threshold=0.99,
                      correct_mistranslations=False,
                      n_cpu=1,
                      quiet=False):

    node_count = max(list(G.nodes())) + 10

    if correct_mistranslations:
        depths = [1, 2, 3]
        if dna_error_threshold > 0.96:
            threshold = list(np.arange(1, dna_error_threshold, -0.01))
        else:
            threshold = list(np.arange(1, 0.97, -0.01)) + list(
                np.arange(0.96, dna_error_threshold, -0.05))
    else:
        depths = [1, 2, 3]
        if family_threshold == 1:
            threshold = [1]
        else:
            if family_threshold > 0.98:
                threshold = [family_threshold]
            elif family_threshold > 0.95:
                threshold = [0.99] + list(np.arange(1, family_threshold,
                                                    -0.02))
            else:
                threshold = [0.99, 0.95] + list(
                    np.arange(0.90, family_threshold, -0.1))

    # precluster for speed
    if correct_mistranslations:
        cdhit_clusters = iterative_cdhit(
            G,
            G.nodes(),
            outdir,
            thresholds=threshold,
            n_cpu=n_cpu,
            quiet=True,
            dna=True,
            # aL=0.6,
            use_local=False,
            accurate=False)
        distances_bwtn_centroids, centroid_to_index = pwdist_edlib(
            G, cdhit_clusters, dna_error_threshold, dna=True, n_cpu=n_cpu)
    else:
        cdhit_clusters = iterative_cdhit(G,
                                         G.nodes(),
                                         outdir,
                                         thresholds=threshold,
                                         n_cpu=n_cpu,
                                         quiet=True,
                                         dna=False)
        distances_bwtn_centroids, centroid_to_index = pwdist_edlib(
            G, cdhit_clusters, family_threshold, dna=False, n_cpu=n_cpu)
    for d in depths:
        search_space = set(G.nodes())
        while len(search_space) > 0:
            # look for nodes to merge
            temp_node_list = list(search_space)
            removed_nodes = set()
            for node in temp_node_list:
                if node in removed_nodes: continue

                if G.degree[node] <= 2:
                    search_space.remove(node)
                    removed_nodes.add(node)
                    continue

                # find neighbouring nodes and cluster their centroid with cdhit
                neighbours = [
                    v for u, v in nx.bfs_edges(G, source=node, depth_limit=d)
                ]

                # find clusters
                index = np.array([
                    centroid_to_index[G.node[neigh]["centroid"].split(";")[0]]
                    for neigh in neighbours
                ],
                                 dtype=int)
                neigh_array = np.array(neighbours)
                n_components, labels = connected_components(
                    csgraph=distances_bwtn_centroids[index][:, index],
                    directed=False,
                    return_labels=True)
                # labels = labels[index]
                clusters = [
                    list(neigh_array[labels == i]) for i in np.unique(labels)
                ]

                for cluster in clusters:
                    # check if there are any to collapse

                    if len(cluster) <= 1: continue

                    # check for conflicts
                    members = list(
                        chain.from_iterable(
                            [G.node[n]['members'] for n in cluster]))

                    if (len(members) == len(set(members))):
                        # no conflicts so merge
                        node_count += 1
                        for neig in cluster:
                            removed_nodes.add(neig)
                            if neig in search_space: search_space.remove(neig)
                        temp_c = cluster.copy()
                        G = merge_nodes(
                            G,
                            temp_c.pop(),
                            temp_c.pop(),
                            node_count,
                            multi_centroid=(not correct_mistranslations))
                        while (len(temp_c) > 0):
                            G = merge_nodes(
                                G,
                                node_count,
                                temp_c.pop(),
                                node_count + 1,
                                multi_centroid=(not correct_mistranslations))
                            node_count += 1
                        search_space.add(node_count)
                    else:
                        if correct_mistranslations:
                            # merge if the centroids don't conflict and the nodes are adjacent in the conflicting genome
                            # this corresponds to a mistranslation where one gene has been split into two in a subset of genomes

                            # work out which nodes each genome has
                            member_to_nodes = defaultdict(set)
                            for n in cluster:
                                for mem in G.node[n]['members']:
                                    member_to_nodes[mem].add(n)

                            should_merge = True
                            for mem in member_to_nodes:
                                if len(member_to_nodes[mem]) <= 1: continue
                                temp_centroids = [
                                    G.node[n]['centroid']
                                    for n in member_to_nodes[mem]
                                ]
                                if len(temp_centroids) != len(
                                        set(temp_centroids)):
                                    # matching centroids so dont merge
                                    should_merge = False
                                sub_G = G.subgraph(member_to_nodes[mem])
                                if not nx.is_connected(sub_G):
                                    should_merge = False

                            if should_merge:
                                node_count += 1
                                for neig in cluster:
                                    removed_nodes.add(neig)
                                    if neig in search_space:
                                        search_space.remove(neig)
                                temp_c = cluster.copy()
                                G = merge_nodes(G,
                                                temp_c.pop(),
                                                temp_c.pop(),
                                                node_count,
                                                multi_centroid=False,
                                                check_merge_mems=False)
                                while (len(temp_c) > 0):
                                    G = merge_nodes(G,
                                                    node_count,
                                                    temp_c.pop(),
                                                    node_count + 1,
                                                    multi_centroid=False,
                                                    check_merge_mems=False)
                                    node_count += 1
                                search_space.add(node_count)
                        else:
                            # there is a conflict in the merge, check if we can split based on neighbours
                            was_merged = True
                            already_merged = set()
                            while was_merged:
                                was_merged = False
                                pos_merges = []
                                for nA in cluster:
                                    if nA in already_merged: continue
                                    best_inter = -1
                                    for nB in cluster:
                                        if nA == nB: continue
                                        if len(
                                                set(G.node[nA]
                                                    ['members']).intersection(
                                                        set(G.node[nB]
                                                            ['members']))) > 0:
                                            continue
                                        temp_inter = len(
                                            set(G.neighbors(nA)).intersection(
                                                set(G.neighbors(nB))))
                                        # if temp_inter==0: continue
                                        if temp_inter > best_inter:
                                            best_inter = temp_inter
                                            best_merge = nB
                                    if best_inter == -1:
                                        # none left to merge with this node
                                        already_merged.add(nA)
                                    else:
                                        pos_merges.append(
                                            (best_inter, nA, best_merge))
                                if len(pos_merges) > 0:
                                    was_merged = True
                                    best_merge = max(pos_merges)
                                    node_count += 1
                                    G = merge_nodes(G, best_merge[1],
                                                    best_merge[2], node_count)
                                    if best_merge[1] in search_space:
                                        search_space.remove(best_merge[1])
                                    if best_merge[2] in search_space:
                                        search_space.remove(best_merge[2])
                                    removed_nodes.add(best_merge[1])
                                    removed_nodes.add(best_merge[2])
                                    cluster.remove(best_merge[1])
                                    cluster.remove(best_merge[2])
                                    cluster.append(node_count)
                                    search_space.add(node_count)

                search_space.remove(node)

    return G



def collapse_paralogs(G, centroid_contexts, max_context=100, quiet=False):
    
    # contexts [centroid] = [[node, member, contig, context], ...]
    node_count = max(list(G.nodes())) + 10

    # first sort by context length, context dist to ensure ties
    #  are broken the same way
    for centroid in centroid_contexts:
        centroid_contexts[centroid] = sorted(centroid_contexts[centroid])

    for centroid in centroid_contexts:
        # calculate distance
        # d = 1 - 1/(abs(contextA-contextB))
        member_paralogs = defaultdict(list)
        for para in centroid_contexts[centroid]:
            member_paralogs[para[1]].append(para)

        ref_paralogs = max(member_paralogs.items(), key=lambda x: len(x[1]))[1]
        # for each paralog find its closest reference paralog
        cluster_dict = defaultdict(set)
        cluster_mems = defaultdict(set)
        for c, ref in enumerate(ref_paralogs):
            cluster_dict[c].add(ref[0])
            cluster_mems[c].add(ref[1])

        for para in centroid_contexts[centroid]:
            d_max = np.inf
            s_max = -np.inf
            best_cluster = None

            if para[1]==ref_paralogs[0][1]:
                # this is the reference so skip
                continue

            # first attempt by shortest path
            for c, ref in enumerate(ref_paralogs):
                if para[1] in cluster_mems[c]:
                    #dont match paralogs of the same isolate
                    continue
                try:
                    d = nx.shortest_path_length(G, ref[0], para[0])
                except nx.NetworkXNoPath:
                    continue
                if d<d_max:
                    d_max = d
                    best_cluster = c

            # if this fails use context
            if d_max==np.inf:
                for c, ref in enumerate(ref_paralogs):
                    if para[1] in cluster_mems[c]:
                        #dont match paralogs of the same isolate
                        continue
                    nodes_ref = {G.node[key]['centroid'].split(";")[0]: val for 
                        (key,val) in nx.single_source_shortest_path_length(G, ref[0], max_context).items()}
                    nodes_para = {G.node[key]['centroid'].split(";")[0]: val for 
                        (key,val) in nx.single_source_shortest_path_length(G, para[0], max_context).items()}
                    s = 0
                    for nr in nodes_ref:
                        if nr in nodes_para:
                            s += 1/(1+np.abs(nodes_ref[nr] - nodes_para[nr]))
                    if s>s_max:
                        s_max = s
                        best_cluster = c
            
            cluster_dict[best_cluster].add(para[0])
            cluster_mems[best_cluster].add(para[1])
        
        # merge
        for cluster in cluster_dict:
            if len(cluster_dict[cluster])<2: continue
            temp_c = cluster_dict[cluster].copy()
            node_count += 1
            G = merge_nodes(G, temp_c.pop(), temp_c.pop(),
                            node_count)
            while (len(temp_c) > 0):
                G = merge_nodes(G, node_count, temp_c.pop(),
                                node_count + 1)
                node_count += 1

    return(G)


def merge_paralogs(G):

    node_count = max(list(G.nodes())) + 10

    # group paralog nodes by centroid
    paralog_centroid_dict = defaultdict(list)
    for node in G.nodes():
        if G.node[node]['paralog']:
            paralog_centroid_dict[G.node[node]['centroid']].append(node)

    # merge paralog nodes that share the same centroid
    for centroid in paralog_centroid_dict:
        node_count += 1
        temp_c = paralog_centroid_dict[centroid]
        G = merge_nodes(G, temp_c.pop(), temp_c.pop(), node_count)
        while (len(temp_c) > 0):
            G = merge_nodes(G, node_count, temp_c.pop(), node_count + 1)
            node_count += 1

    return (G)


def clean_misassembly_edges(G, edge_support_threshold):

    bad_edges = set()
    max_weight = 0

    # remove edges with low support near contig ends
    for node in G.nodes():
        max_weight = max(max_weight, G.nodes[node]['size'])
        for neigh in G.neighbors(node):
            if G.node[neigh]['hasEnd']:
                if G[node][neigh]['weight'] < edge_support_threshold:
                    bad_edges.add((node, neigh))

    # remove edges that have much lower support than the nodes they connect
    for edge in G.edges():
        if float(G.edges[edge]['weight']) < (0.05 * min(
                int(G.node[edge[0]]['size']), int(G.node[edge[1]]['size']))):
            if float(G.edges[edge]['weight']) < edge_support_threshold:
                bad_edges.add(edge)

    for edge in bad_edges:
        if G.has_edge(edge[0], edge[1]):
            G.remove_edge(edge[0], edge[1])

    return (G)


def identify_possible_highly_variable(G,
                                      cycle_threshold_max=20,
                                      cycle_threshold_min=5,
                                      size_diff_threshold=0.5):

    # add family paralog attribute to nodes
    for node in G.nodes():
        G.node[node]['highVar'] = 0

    # find all the cycles shorter than cycle_threshold
    complete_basis = []
    for c in nx.connected_components(G):
        sub_G = G.subgraph(c)
        basis = nx.cycle_basis(sub_G, list(sub_G.nodes())[0])
        complete_basis += [
            set(b) for b in basis if len(b) <= cycle_threshold_max
        ]

    # remove cycles that are too short
    complete_basis = [b for b in complete_basis if len(b) >= 3]

    # merge cycles with more than one node in common (nested)
    if len(complete_basis) < 1:
        return G

    merged_basis = [[1, set(complete_basis[0])]]
    for b in complete_basis[1:]:
        b = set(b)
        merged = False
        for i, mb in enumerate(merged_basis):
            if len(mb[1].intersection(b)) > 1:
                merged = True
                merged_basis[i][0] += 1
                merged_basis[i][1] |= b
        if not merged:
            merged_basis.append([1, b])

    for b in merged_basis:
        if b[0] < cycle_threshold_min: continue
        max_size = max([G.node[node]['size'] for node in b[1]])
        for node in b[1]:
            if G.node[node]['size'] < (size_diff_threshold * max_size):
                G.node[node]['highVar'] = 1

    return G
