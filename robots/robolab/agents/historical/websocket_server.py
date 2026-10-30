# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Small OpenPI-compatible WebSocket server with NumPy msgpack support."""

from __future__ import annotations

import asyncio
import functools
import http
import logging
import time
import traceback
from typing import Any

import msgpack
import numpy as np
import websockets
import websockets.asyncio.server as websocket_server
import websockets.frames

logger = logging.getLogger(__name__)


def _pack_numpy(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        if value.dtype.kind in ("V", "O", "c"):
            raise ValueError(f"Unsupported NumPy dtype: {value.dtype}")
        return {
            b"__ndarray__": True,
            b"data": value.tobytes(),
            b"dtype": value.dtype.str,
            b"shape": value.shape,
        }
    if isinstance(value, np.generic):
        return {
            b"__npgeneric__": True,
            b"data": value.item(),
            b"dtype": value.dtype.str,
        }
    return value


def _unpack_numpy(value: dict) -> Any:
    if b"__ndarray__" in value:
        return np.ndarray(
            buffer=value[b"data"],
            dtype=np.dtype(value[b"dtype"]),
            shape=value[b"shape"],
        )
    if b"__npgeneric__" in value:
        return np.dtype(value[b"dtype"]).type(value[b"data"])
    return value


Packer = functools.partial(msgpack.Packer, default=_pack_numpy)
unpackb = functools.partial(msgpack.unpackb, object_hook=_unpack_numpy)


class WebsocketPolicyServer:
    def __init__(self, policy: Any, host: str = "0.0.0.0", port: int = 8000) -> None:
        # WebsocketPolicyServer accepts any policy that implement
        # policy.metadata and policy.infer(request_packed_data)
        self.policy = policy
        self.host = host
        self.port = port
        self._harness_connected = False

    def serve_forever(self) -> None:
        asyncio.run(self.run())

    async def run(self) -> None:
        async with websocket_server.serve(
            self._handler,
            self.host,
            self.port,
            compression=None,
            max_size=None,
            process_request=_health_check,
            ping_interval=60,
            ping_timeout=120,
        ) as server:
            await server.serve_forever()

    async def _handler(self, websocket: websocket_server.ServerConnection) -> None:
        managed = self.policy.metadata.get("policy") == "harness"
        if managed and self._harness_connected:
            await websocket.close(
                code=1013, reason="Harness already has an active client"
            )
            return
        if managed:
            self._harness_connected = True
            self.policy.connect()
        try:
            await self._serve_connection(websocket, managed=managed)
        finally:
            if managed:
                try:
                    self.policy.close()
                finally:
                    self._harness_connected = False

    async def _infer_harness(self, websocket, request):
        # Keep heartbeats and disconnect detection alive during long model calls.
        worker = asyncio.create_task(asyncio.to_thread(self.policy.infer, request))
        disconnected = asyncio.create_task(websocket.wait_closed())
        try:
            await asyncio.wait(
                (worker, disconnected), return_when=asyncio.FIRST_COMPLETED
            )
            if disconnected.done():
                self.policy.disconnect()
                return None
            return worker.result()
        finally:
            if not worker.done():
                self.policy.disconnect()
            await asyncio.gather(worker, return_exceptions=True)
            disconnected.cancel()
            await asyncio.gather(disconnected, return_exceptions=True)

    async def _serve_connection(self, websocket, *, managed: bool) -> None:
        logger.info("Connection from %s opened", websocket.remote_address)
        packer = Packer()
        await websocket.send(packer.pack(self.policy.metadata))
        previous_total = None

        while True:
            try:
                started = time.monotonic()
                request = unpackb(await websocket.recv())
                inference_started = time.monotonic()
                response = (
                    await self._infer_harness(websocket, request)
                    if managed
                    else self.policy.infer(request)
                )
                if response is None:
                    return
                response["server_timing"] = {
                    "infer_ms": (time.monotonic() - inference_started) * 1000,
                }
                if previous_total is not None:
                    response["server_timing"]["prev_total_ms"] = previous_total * 1000
                await websocket.send(packer.pack(response))
                previous_total = time.monotonic() - started
            except websockets.ConnectionClosed:
                logger.info("Connection from %s closed", websocket.remote_address)
                return
            except Exception:
                await websocket.send(traceback.format_exc())
                await websocket.close(
                    code=websockets.frames.CloseCode.INTERNAL_ERROR,
                    reason="Internal server error. Traceback included in previous frame.",
                )
                raise


def _health_check(
    connection: websocket_server.ServerConnection,
    request: websocket_server.Request,
) -> websocket_server.Response | None:
    if request.path == "/healthz":
        return connection.respond(http.HTTPStatus.OK, "OK\n")
    return None
