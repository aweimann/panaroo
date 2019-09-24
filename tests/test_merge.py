# test if the panaroo merge function is working correctly
from panaroo.__main__ import main
from panaroo.merge_graphs import main as merge_main
import numpy as np
import sys
import os
import tempfile


def test_merge(datafolder):

    # run panaroo on pairs of gff3 files
    with tempfile.TemporaryDirectory() as tmpdirA:
        with tempfile.TemporaryDirectory() as tmpdirB:
            sys.argv = ["", "-i", 
                datafolder + "aa1.gff", 
                datafolder + "aa2.gff", 
                "-o", tmpdirA]
            main()

            sys.argv = ["", "-i", 
                datafolder + "aa3.gff", 
                datafolder + "aa4.gff", 
                "-o", tmpdirB]
            main()

            # merge the result
            sys.argv = ["", "-d", 
                tmpdirA, 
                tmpdirB, 
                "-o", datafolder]
            merge_main()

    assert os.path.isfile(datafolder + "merged_final_graph.gml")

    # read gene p/a file
    pa = np.genfromtxt(datafolder + "gene_presence_absence.Rtab",
        delimiter="\t", skip_header=1)

    assert pa.shape == (5156, 5)
    assert np.sum(pa[:,1:])==20426

    # read struct p/a file
    pa = np.genfromtxt(datafolder + "struct_presence_absence.Rtab",
        delimiter="\t", skip_header=1)

    assert pa.shape == (135, 5)
    assert np.sum(pa[:,1:])==319

    return