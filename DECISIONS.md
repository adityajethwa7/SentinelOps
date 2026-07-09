# Architectural Decisions & Assumptions

- **LLM Independence**: Abstracted Qwen Model Studio calls inside `qwen_client.py`. Tests use mock clients to simulate tool-call responses to avoid flakey tests and API limits.
- **Data Persistence**: Single-node SQLite database (`data/sentinelops.db`) is used for the store. A standard NetworkX DiGraph is rehydrated from the SQLite edge list to determine incident similarity and fix weighting.
- **Confidence Model**: Used Beta-Binomial Bayesian updating. Started with a Beta(2,2) prior to ensure cold starts require human intervention. Used the 10th percentile LCB (Lower Confidence Bound) instead of the mean to inherently punish thin evidence (e.g., 1/1 successes vs 18/20 successes).
- **Tool Calling Limitation**: Alibaba Model Studio does not support `stream=True` alongside `tools=[]`. All agent interactions were designed as synchronous, non-streaming completion calls.
- **Arbitration Logic**: Built a strict deterministic rules engine for arbitration (gate). LLMs handle qualitative mapping (Triage, Investigation, Planning), but Python code handles the go/no-go decision.
- **Safety**: `kube-system` (and other user-defined namespaces) are explicitly denylisted in the Playbook Registry and the Arbitration Agent. Actions against these will hard-fail.
