# Headline-run rule

For one model on one hardware configuration, the headline figure comes from the first run in this order:

1. A run on a pinned engine (`engine.pre_pin: false`) comes before a pre-pin run or a run whose engine is unknown (`engine.pre_pin` true or null).
2. A run on the house speed protocol, `speed-house/v1`, comes before a run on any other protocol.
3. Then the run with the most repetitions of the speed pass (`metrics.repetitions`, 1 when absent).
4. Then the most recent run.

Only a distinct run that ended `ok`, with a known topology and a measured solo speed, can be the headline: a copy of another run (`duplicate_of`), a speculative-decoding run with a drafter, the treatment arm of an A/B test (`engine_args.ab_arm: "treatment"`, or NVLink switched off in software, `topology.p2p: "off-software"`), and a run of the uncensored-model study or a copy of one (refusal rates only) never are.
