# Clustering and scoring

- **What is vectorised:** the stage-02 `issue` phrase. The model already rewrote every message, in any language, as a short normalised English phrase, so grouping needs no second model: hashed TF-IDF over words, word bigrams and character trigrams, with a small synonym map (`app/pipeline/vectors.py`, 1,024 dims, L2-normalised). No quota, no network, identical offline and live.
- **Greedy clustering inside an intent:** walk messages in time order; join the most similar cluster if cosine to its centroid >= 0.42, else start a new one. Centroids update as a running mean. Clusters of 1-2 messages fold into that intent's `-other` bucket, which is counted but never becomes a card.
- **Baseline assignment:** a baseline message counts for the cluster that holds its nearest shift neighbour of the same intent, when cosine >= 0.42. Nearest neighbour rather than centroid, so broad clusters are not starved. It never creates clusters.
- **Lift:** `(n_shift_c / n_shift) / max(n_base_c / n_base, 0.5 / n_base)`. The floor stops a brand-new issue from dividing by zero; such clusters are marked `new`.
- **Score:** `impact^0.8 * (1 + urgency) * (1 + 0.5 * log2(max(lift, 1)))`, where (size and money lead; novelty breaks ties, so five unusual messages never outrank fifty angry customers)
  - `impact = customers * (1 + 2 * vip_share) * (1 + sar_at_risk / 5000)`
  - `urgency = mean(max(0, -sentiment)) / 2 + share(urgency == high)`
- **Auto-handled:** clusters whose intent is on the auto-handle list in `_shared/policies.md` become the one-line summary, not cards, unless their lift >= 3 (then a person should know).
