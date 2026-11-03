# Design note

Design note (brownfield) for plan plan_bbf60b3f17
Summary: Locate the project's existing entry point, create a minimal runproject.py launcher in the project root with a __main__ guard that delegates to it and propagates the exit status, add tests for import-safety and launch behavior, then run validation.
Top-level entries: .pytest_cache, README.md, app, pytest.ini, requirements.txt, tests
Approach: apply scoped Workspace edits per task; gate all shell via CommandRunner.
