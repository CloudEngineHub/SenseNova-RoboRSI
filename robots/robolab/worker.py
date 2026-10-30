# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Serve native RoboLab operations on the simulator's owning main thread."""

from __future__ import annotations

import argparse
from pathlib import Path

from roborsi.evaluation.messages import Action, Task
from roborsi.evaluation.service_host import load_factory
from roborsi.utils.rpc import RpcFacade
from roborsi.utils.rpc.main_thread_serve import MainThreadServeMixin
from robots.robolab.episode import RoboLabEpisode


class RoboLabWorker(MainThreadServeMixin, RpcFacade):
    def __init__(self, episode: RoboLabEpisode) -> None:
        super().__init__()
        self.episode = episode
        self._rpc["request"] = self.request

    def request(self, method: str, payload: dict) -> dict:
        if method == "start":
            return self.episode.start(
                Task.from_dict(payload["task"]), payload["episode_id"]
            ).as_dict()
        if method == "step":
            return self.episode.step(Action.from_dict(payload)).as_dict()
        if method == "finish":
            return self.episode.finish().as_dict()
        if method == "close":
            self.episode.close()
            return {}
        raise ValueError("unsupported RoboLab worker operation")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--factory", default="robots.robolab.native:make_runtime")
    args = parser.parse_args()
    runtime = load_factory(args.factory)(args.directory)
    episode = RoboLabEpisode(args.directory, runtime)
    worker = RoboLabWorker(episode)
    try:
        worker.serve(
            transport="http", host="127.0.0.1", port=args.port, parent_watch=True
        )
    finally:
        episode.close()


if __name__ == "__main__":
    main()
