# Study-area definition and comparison with the earlier notebook

Every number in the paper and in this repository uses one study-area filter. Hexagon centroids are computed in EPSG:3035 and joined to the country polygons; hexagons in Russia and Turkey, hexagons outside every polygon, and hexagons with no charging point are dropped. This gives 6,283 hexagons and 11,877 points. Section A of the check table (39 checks) tests the paper's numbers on this filter.

An earlier version of the analysis notebook computed centroids in EPSG:4326. Because the two projections place a few coastal centroids slightly differently, that filter keeps one 2-point coastal hexagon that the current filter drops, and drops one 1-point hexagon that the current filter keeps. Its total is 11,878 points.

Section B of the check table (100 checks) reruns all sweeps on the earlier filter and compares them with the notebook's output files in `data/reference/`. All match exactly. Section B only shows that the extracted code is the same as the notebook code; it is not the filter used in the paper.

## Place names of the saturated hexagons

Three of the seven saturated hexagons were renamed from their coordinates, because the names in the paper's Appendix D did not match them:

| Centroid | Name used here | Name in the paper draft |
|---|---|---|
| 53.38 N, 2.94 W | Chester / Merseyside (UK) | Wales–England border |
| 52.07 N, 0.78 W | Milton Keynes (UK) | East Midlands |
| 58.89 N, 14.50 E | Laxå, Örebro / Västra Götaland border (SE) | Örebro–Värmland |
