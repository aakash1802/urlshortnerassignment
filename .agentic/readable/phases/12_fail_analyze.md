# Failure analysis / recovery decision

- Task: `t5`
- Error: [failure_category=truncated_response] Developer agent failed for t5 (Write pytest test suite): Model response truncated (stop_reason=max_tokens)
- Category: `output_truncated`
- Strategy: `reduce_scope`
- Retry count: `0`
- Cap: `10`
- Recommendation: `retry`
- Corrective action: Split the task into smaller dependent subtasks or reduce output size.
- Inputs change: `True`
- Scope change: `True`
- Graph change: `True`
- Human approval required: `False`
- Reason: Truncated/oversized output; reduce generation scope (1/2). [failure_category=truncated_response] Developer agent failed for t5 (Write pytest test suite): Model response truncated (stop_reason=max_tokens)
- Prefer replan: `False`
