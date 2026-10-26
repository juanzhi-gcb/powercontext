Hybrid search combines a full-text branch and a vector branch, then fuses the two rankings.
seekdb performs the fusion inside the database with reciprocal rank fusion, so a client never has to
fetch both candidate lists and merge them itself. The rank window and rank constant control how
aggressively the two branches are blended.
