Round 1 (DeepSeek): clusters were looked up by factor NAME; the real cluster_labels.csv is
keyed by the JKP code — every cluster came out empty on the real data (and every library
family defaulted to 'technical'). Fixed in module and test fixture. The test also counted
one weighting against a query of both, and called a non-existent strategy_library.get.
Real data: 153 factors, 142 library entries, 10 adoption candidates (post-publication t > 3).
