# Docker Python tests

- `test_docker_client_basic.py`: Starts/stops a runner-core container and exercises a simple exec call.
- `test_docker_client.py`: Clones a repo in a container using `DockerClient` end-to-end (start, clone, checkout, setup, test).
- `test_compat_rewrite.py`: Runs the collections.abc rewrite helper inside a container to ensure it succeeds.
- `test_session_requests.py`: Uses `SessionRunner` with the requests smoke config to verify clone/checkout/setup/test orchestration and reporting.
