from prokka import process_prokka_input
from cdhit import run_cdhit
from generate_network import generate_network
from clean_network import *
import os
import argparse
import tempfile
from Bio import SeqIO
import shutil
import networkx as nx


def is_valid_file(parser, arg):
    if not os.path.exists(arg):
        parser.error("The file %s does not exist!" % arg)
    else:
        return arg

def is_valid_folder(parser, arg):
    if not os.path.isdir(arg):
        parser.error("The folder %s does not exist!" % arg)
    else:
        return arg


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("-c", "--threshold", dest="id",
                    help="sequence identity threshold (default=0.95)",
                    type=float, default=0.95)

    parser.add_argument("-f", "--family_threshold", dest="family_threshold",
                    help="protein family sequence identity threshold (default=0.7)",
                    type=float, default=0.7)

    parser.add_argument("--len_dif_percent", dest="len_dif_percent",
                    help="length difference cutoff (default=0.95)",
                    type=float, default=0.95)

    parser.add_argument("-i", "--input", dest="input_files", required=True,
                    help="input GFF3 files (usually output from running Prokka)",
                    type=argparse.FileType('rU'), nargs='+')

    parser.add_argument("-o", "--out_dir", dest="output_dir", required=True,
                    help="location of an output directory",
                    type=lambda x: is_valid_folder(parser, x))

    parser.add_argument("--min_trailing_support",
                    dest="min_trailing_support",
                    help=("minimum cluster size to keep a gene called at the "
                        + "end of a contig (default=2)"),
                    type=int, default=2)

    parser.add_argument("--max_cycle_size",
                    dest="max_cycle_size",
                    help=("maximum cycle  size for collapsing gene families "
                        + "(default=20)"),
                    type=int, default=20)

    parser.add_argument("--no_split", dest="split_paralogs",
                    help="don't split paralogs",
                    action='store_false',
                    default=True)

    parser.add_argument("-t", "--threads", dest="n_cpu",
                    help="number of threads to use (default=1)",
                    type=int, default=1)

    args = parser.parse_args()

    # make sure trailing forward slash is present
    args.output_dir = os.path.join(args.output_dir, "")

    # Create temporary directory
    temp_dir = tempfile.mkdtemp(dir=args.output_dir)

    # convert input GFF3 files into summary files
    process_prokka_input(args.input_files, args.output_dir)

    # Cluster protein sequences using cdhit
    cd_hit_out = args.output_dir + "combined_protein_cdhit_out.txt"
    run_cdhit(input_file=args.output_dir + "combined_protein_CDS.fasta",
        output_file=cd_hit_out,
        id=args.id,
        s=args.len_dif_percent,
        n_cpu=args.n_cpu)

    # generate network from clusters and adjacency information
    G = generate_network(
            cluster_file = cd_hit_out+".clstr",
            data_file = args.output_dir + "gene_data.csv",
            prot_seq_file = args.output_dir + "combined_protein_CDS.fasta",
            split_paralogs = args.split_paralogs)

    # write out pre-filter graph in GML format
    nx.write_gml(G, args.output_dir + "pre_filt_graph.gml")

    # remove low support trailing ends
    G = trim_low_support_trailing_ends(G, min_support=args.min_trailing_support,
        max_recursive=2)

    # clean up translation errors and gene families
    G = collapse_families(G,
        cycle_threshold=args.max_cycle_size,
        family_threshold=args.family_threshold,
        outdir=temp_dir,
        dna_error_threshold=0.99,
        correct_mistranslations=True)

    # write out graph in GML format
    nx.write_gml(G, args.output_dir + "final_graph.gml")

    # remove temp TemporaryDirectory
    shutil.rmtree(temp_dir)

    return


if __name__ == '__main__':
    main()
