#Reduce a Panaroo graph to only keep some isolates

You can subset a Panaroo graph and only keep genes and gene connections that derive from an input list of isolates. This is useful if you want to reduce the complexity of the graph e.g. you could pick a representative isolate for every genomic cluster derived by PopPUNK or fastBaps or if you want to just focus on all isolates of a particular cluster.

The script expects the Panaroo graph *final_graph.gml*, a list of isolates *isols.txt* (the header line is ignored) and an output file for the reduced graph *final_graph_reduced.gml*:

```python reduce_graph.py final_graph.gml  isols.txt final_graph_reduced.gml```

For help run
```python reduce_graph.py -h``` 




