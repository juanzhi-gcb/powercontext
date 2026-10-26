Quantisation reduces model size and memory bandwidth at the cost of small numerical error.
Int8 quantisation usually keeps retrieval quality within a couple of points of the float baseline,
measured with recall at k over a labelled query set. The trade is worth it when the model must load
quickly in a browser.
