all-MiniLM-L6-v2 is a six-layer transformer that maps a sentence to a 384-dimensional unit vector.
It is trained for semantic similarity, so paraphrases land close together even when they share few words.
The quantised build stores weights as int8 and is roughly a quarter of the float32 size.
