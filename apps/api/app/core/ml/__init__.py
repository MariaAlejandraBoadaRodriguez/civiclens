"""ML Lab (slice 5d): red flags for human review and an honest spend forecast.

Pure functions on pandas frames read from the star schema. Every model uses a fixed seed so
two runs on the same data return the same ranking and the same metrics. Texts (model cards,
reasons) live in the API catalogs; results here hold stable ids and numbers only.
"""

SEED = 42
