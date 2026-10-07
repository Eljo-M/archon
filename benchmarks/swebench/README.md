# SWE-bench Lite integration

This directory owns evaluation integration (E-01). No benchmark has been executed yet. Use the [official evaluation harness](https://www.swebench.com/SWE-bench/guides/evaluation/) on a Linux Docker host with sufficient storage and memory.

Required prediction format:

```json
{"instance_id":"owner__repo-issue","model_name_or_path":"archon-baseline","model_patch":"unified git diff"}
```

After installing the official `swebench` package and supplying actual predictions, the initial invocation is:

```sh
python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Lite --predictions_path predictions.jsonl --max_workers 1 --run_id unique-run-id
```

Pin the dataset, harness version, environment image and model configuration before publishing comparisons. Use a new run ID after changing predictions to avoid cached results. Keep dataset instances designated for held-out evaluation out of distillation/training. Record infrastructure failures separately from unresolved issues.

The ordinary repair-loop test command is not yet the SWE-bench oracle. E-01 will implement instance provisioning, trusted test-patch handling and trace-to-prediction export before measuring a score.
