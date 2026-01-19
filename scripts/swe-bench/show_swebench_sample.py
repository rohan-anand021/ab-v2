from __future__ import annotations

import json
import sys


def main() -> None:
    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("Install `datasets` to load SWE-bench (e.g., `uv add datasets`).")

    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test", streaming=True)
    first = next(iter(ds))
    print(json.dumps(first, indent=2, default=str))


if __name__ == "__main__":
    main()
