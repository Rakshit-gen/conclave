"""Standalone entrypoint for one demo agent: `python -m examples.pipeline.serve <agent> <port>`.

Run three of these (different `<agent>`, different `<port>`) as separate OS
processes and you have three genuinely independent A2A agents talking over
real HTTP — which is the whole point of the pipeline demo in run.py.
"""

from __future__ import annotations

import sys

import uvicorn

from . import agents

_BUILDERS = {
    "researcher": agents.researcher_server,
    "writer": agents.writer_server,
    "reviewer": agents.reviewer_server,
}


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in _BUILDERS:
        options = "|".join(_BUILDERS)
        print(f"usage: python -m examples.pipeline.serve {{{options}}} <port>", file=sys.stderr)
        raise SystemExit(2)
    name, port = sys.argv[1], int(sys.argv[2])
    server = _BUILDERS[name]()
    uvicorn.run(server.app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
