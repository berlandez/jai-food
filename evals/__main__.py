"""One-command entry point: python -m evals

--offline   do not collect the live Claude graders
--llm       run only the live Claude graders
Any other arguments are passed through to pytest.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    args = list(sys.argv[1:] if argv is None else argv)
    offline = "--offline" in args
    llm_only = "--llm" in args
    if offline and llm_only:
        print("Choose one of --offline or --llm.", file=sys.stderr)
        return 2
    args = [a for a in args if a not in ("--offline", "--llm")]
    if offline:
        args = ["-m", "not llm", *args]
    elif llm_only:
        args = ["-m", "llm", *args]
    import pytest

    return pytest.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
