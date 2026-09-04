#!/usr/bin/env python3
from typed_export import cli_main  # noqa: I001 - executable sibling import.


if __name__ == "__main__":
    raise SystemExit(cli_main("parquet"))
