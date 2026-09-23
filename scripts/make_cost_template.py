from __future__ import annotations

import argparse
from pathlib import Path

from construction_os.importers.cost_template import make_template


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    make_template(Path(a.out))
    print(f"cost template: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
