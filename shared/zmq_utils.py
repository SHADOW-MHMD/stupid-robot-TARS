"""
ZeroMQ Networking Utilities for TARS Distributed Dual-Brain Robot.

Provides high-performance, robust, and resilient ZeroMQ abstractions:
- ZMQPublisher: Drop-oldest PUB wrapper for high-throughput video & telemetry streaming.
- ZMQSubscriber: Topic-filtered SUB wrapper with non-blocking receive & buffering.
- ZMQReqClient: Lazy Pirate pattern REQ client with auto-reconnection and retry loops.
- ZMQRepServer: REP server for handling inter-brain control and tool RPC calls.
- Serialization and framing helpers for JSON payloads, binary headers, and configuration loading.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import struct
import threading
import time
from typing import Any

import zmq

logger = logging.getLogger("TARS.ZMQUtils")


# ---------------------------------------------------------------------------
# Framing & Serialization Helpers
# ---------------------------------------------------------------------------


def serialize_json(data: Any) -> bytes:
    """Serialize Python object to UTF-8 encoded JSON bytes."""
    try:
        return json.dumps(data, separators=(",", ":"), default=str).encode("utf-8")
    except Exception as e:
        logger.error(f"Error serializing JSON data: {e}")
        return b"{}"


def deserialize_json(raw: bytes | str | None) -> Any | None:
    """Safely deserialize JSON from bytes or string. Returns None on decode failure."""
    if raw is None:
        return None
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as e:
        logger.warning(f"Failed to decode JSON payload: {e}")
        return None


def encode_frame_header(
    frame_len: int, frame_id: int, timestamp_ms: int, use_64bit_ts: bool = True
) -> bytes:
    """
    Pack binary video frame header.
    If use_64bit_ts is True (default): !IIQ (16 bytes: 4-byte length, 4-byte ID, 8-byte uint64 timestamp).
    Else: !III (12 bytes: 4-byte length, 4-byte ID, 4-byte uint32 timestamp).
    """
    if use_64bit_ts:
        return struct.pack("!IIQ", frame_len, frame_id, int(timestamp_ms))
    return struct.pack("!III", frame_len, frame_id, int(timestamp_ms) & 0xFFFFFFFF)


def decode_frame_header(header_bytes: bytes) -> tuple[int, int, int] | None:
    """
    Unpack standard 16-byte binary video frame header (!IIQ).
    Returns: (frame_length, frame_id, timestamp_ms) or None if malformed.
    """
    if not isinstance(header_bytes, (bytes, bytearray)) or len(header_bytes) < 16:
        return None
    try:
        return struct.unpack("!IIQ", header_bytes[:16])
    except struct.error:
        return None


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """
    Load centralized config.json with fallback resolution.
    Searches:
    1. Explicit config_path
    2. Environment variable TARS_CONFIG
    3. Current working directory ./config.json
    4. Repo root /home/Mishal/robot/TARS/config.json
    """
    candidate_paths: list[Path] = []
    if config_path:
        candidate_paths.append(Path(config_path))
    if os.environ.get("TARS_CONFIG"):
        candidate_paths.append(Path(os.environ["TARS_CONFIG"]))

    candidate_paths.append(Path("config.json"))
    candidate_paths.append(Path(__file__).resolve().parent.parent / "config.json")
    candidate_paths.append(Path("/home/Mishal/robot/TARS/config.json"))

    for p in candidate_paths:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to parse config file at {p}: {e}")
                raise

    raise FileNotFoundError(
        f"Could not locate config.json in candidate paths: {[str(p) for p in candidate_paths]}"
    )


# ---------------------------------------------------------------------------
# ZMQ Publisher
# ---------------------------------------------------------------------------


class ZMQPublisher:
    """
    ZeroMQ Publisher wrapper supporting topic-based multi-part messaging,
    drop-oldest queue management, and non-blocking streaming.
    """

    def __init__(
        self,
        endpoint: str | int = "",
        port: int | None = None,
        host: str = "*",
        bind: bool = True,
        sndhwm: int = 10,
        conflate: bool = False,
        sndtimeo_ms: int = 100,
        context: zmq.Context | None = None,
    ) -> None:
        if port is not None:
            endpoint = f"tcp://{host}:{port}"
        elif isinstance(endpoint, int):
            endpoint = f"tcp://{host}:{endpoint}"
        elif not str(endpoint).startswith("tcp://") and not str(endpoint).startswith("inproc://") and not str(endpoint).startswith("ipc://"):
            endpoint = f"tcp://{host}:{endpoint}" if endpoint else f"tcp://{host}:5555"
        self.endpoint = str(endpoint)
        self.bind_mode = bind
        self._owned_context = False
        self.context = context or zmq.Context.instance()
        self.socket = self.context.socket(zmq.PUB)
        self._lock = threading.Lock()

        self.socket.setsockopt(zmq.SNDHWM, sndhwm)
        if conflate:
            try:
                self.socket.setsockopt(zmq.CONFLATE, 1)
            except zmq.ZMQError as e:
                logger.warning(f"Could not set ZMQ_CONFLATE on PUB socket: {e}")

        if sndtimeo_ms > 0:
            self.socket.setsockopt(zmq.SNDTIMEO, sndtimeo_ms)

        self.socket.setsockopt(zmq.LINGER, 0)

        if self.bind_mode:
            self.socket.bind(self.endpoint)
            logger.info(f"ZMQPublisher bound to {self.endpoint}")
        else:
            self.socket.connect(self.endpoint)
            logger.info(f"ZMQPublisher connected to {self.endpoint}")

    def send_multipart(
        self,
        parts: list[bytes | str | dict | list | Any],
        flags: int = 0,
    ) -> bool:
        """
        Send multipart message over PUB socket.
        Automatically serializes strings and dicts/lists to bytes.
        Returns True on success, False on drop or error.
        """
        with self._lock:
            try:
                byte_parts: list[bytes] = []
                for part in parts:
                    if isinstance(part, bytes):
                        byte_parts.append(part)
                    elif isinstance(part, str):
                        byte_parts.append(part.encode("utf-8"))
                    elif isinstance(part, (dict, list)):
                        byte_parts.append(serialize_json(part))
                    else:
                        byte_parts.append(str(part).encode("utf-8"))

                self.socket.send_multipart(byte_parts, flags=flags)
                return True
            except zmq.Again:
                logger.debug(f"Publisher send dropped due to timeout (EAGAIN) on {self.endpoint}")
                return False
            except zmq.ZMQError as e:
                logger.warning(f"Publisher ZMQError on {self.endpoint}: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error in send_multipart: {e}")
                return False

    def send_json(self, topic: str | bytes, data: Any, flags: int = 0) -> bool:
        """Publish JSON payload on a given topic: [topic, json_bytes]."""
        topic_bytes = topic if isinstance(topic, bytes) else topic.encode("utf-8")
        return self.send_multipart([topic_bytes, serialize_json(data)], flags=flags)

    def send_string(self, topic: str | bytes, text: str, flags: int = 0) -> bool:
        """Publish plain string message on a given topic: [topic, text_bytes]."""
        topic_bytes = topic if isinstance(topic, bytes) else topic.encode("utf-8")
        return self.send_multipart([topic_bytes, text.encode("utf-8")], flags=flags)

    def publish_video_frame(
        self,
        topic: str | bytes,
        frame_id: int,
        timestamp_ms: int | float,
        jpeg_bytes: bytes,
        flags: int = 0,
    ) -> bool:
        """
        Publish video frame multi-part message.
        Format: [topic, 16-byte !IIQ header, jpeg_bytes]
        """
        topic_bytes = topic if isinstance(topic, bytes) else topic.encode("utf-8")
        header = encode_frame_header(len(jpeg_bytes), frame_id, int(timestamp_ms))
        return self.send_multipart([topic_bytes, header, jpeg_bytes], flags=flags)

    def close(self) -> None:
        """Close socket and clean up context if owned."""
        with self._lock:
            if self.socket and not self.socket.closed:
                self.socket.close(linger=0)
            if self._owned_context and self.context and not self.context.closed:
                self.context.term()

    def __enter__(self) -> ZMQPublisher:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# ---------------------------------------------------------------------------
# ZMQ Subscriber
# ---------------------------------------------------------------------------


class ZMQSubscriber:
    """
    ZeroMQ Subscriber wrapper with topic subscriptions, non-blocking polling,
    drop-oldest buffer handling, and safe payload deserialization.
    """

    def __init__(
        self,
        endpoint: str | int = "",
        port: int | None = None,
        host: str = "localhost",
        topics: str | bytes | list[str | bytes] = b"",
        topic: str | bytes | None = None,
        bind: bool = False,
        rcvhwm: int = 10,
        conflate: bool = False,
        rcvtimeo_ms: int | None = None,
        context: zmq.Context | None = None,
    ) -> None:
        if port is not None:
            endpoint = f"tcp://{host}:{port}"
        elif isinstance(endpoint, int):
            endpoint = f"tcp://{host}:{endpoint}"
        elif endpoint and not str(endpoint).startswith("tcp://") and not str(endpoint).startswith("inproc://") and not str(endpoint).startswith("ipc://"):
            endpoint = f"tcp://{host}:{endpoint}"
        elif not endpoint:
            endpoint = f"tcp://{host}:5558"
        self.endpoint = str(endpoint)
        if topic is not None:
            topics = topic
        self.bind_mode = bind
        self._owned_context = False
        self.context = context or zmq.Context.instance()
        self.socket = self.context.socket(zmq.SUB)

        self.socket.setsockopt(zmq.RCVHWM, rcvhwm)
        if conflate:
            try:
                self.socket.setsockopt(zmq.CONFLATE, 1)
            except zmq.ZMQError as e:
                logger.warning(f"Could not set ZMQ_CONFLATE on SUB socket: {e}")

        if rcvtimeo_ms is not None and rcvtimeo_ms >= 0:
            self.socket.setsockopt(zmq.RCVTIMEO, rcvtimeo_ms)

        self.socket.setsockopt(zmq.LINGER, 0)

        # Set up topic subscriptions
        if isinstance(topics, (str, bytes)):
            self.subscribe(topics)
        elif isinstance(topics, list):
            for t in topics:
                self.subscribe(t)

        if self.bind_mode:
            self.socket.bind(self.endpoint)
            logger.info(f"ZMQSubscriber bound to {self.endpoint}")
        else:
            self.socket.connect(self.endpoint)
            logger.info(f"ZMQSubscriber connected to {self.endpoint}")

        self._poller = zmq.Poller()
        self._poller.register(self.socket, zmq.POLLIN)

    def subscribe(self, topic: str | bytes) -> None:
        """Subscribe to a topic."""
        topic_bytes = topic if isinstance(topic, bytes) else topic.encode("utf-8")
        self.socket.setsockopt(zmq.SUBSCRIBE, topic_bytes)

    def unsubscribe(self, topic: str | bytes) -> None:
        """Unsubscribe from a topic."""
        topic_bytes = topic if isinstance(topic, bytes) else topic.encode("utf-8")
        self.socket.setsockopt(zmq.UNSUBSCRIBE, topic_bytes)

    def recv_multipart(
        self,
        flags: int = 0,
        timeout_ms: int | None = None,
    ) -> list[bytes] | None:
        """
        Receive a multi-part message.
        If timeout_ms is specified, polls for incoming data.
        Returns list of byte parts or None on timeout/EAGAIN.
        """
        try:
            if timeout_ms is not None:
                socks = dict(self._poller.poll(timeout_ms))
                if self.socket not in socks:
                    return None

            return self.socket.recv_multipart(flags=flags)
        except zmq.Again:
            return None
        except zmq.ZMQError as e:
            logger.warning(f"Subscriber ZMQError on {self.endpoint}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in recv_multipart: {e}")
            return None

    def recv_json(
        self,
        flags: int = 0,
        timeout_ms: int | None = None,
    ) -> tuple[str, Any] | None:
        """
        Receive topic-filtered JSON message.
        Returns: (topic_string, parsed_json_object) or None.
        """
        parts = self.recv_multipart(flags=flags, timeout_ms=timeout_ms)
        if not parts:
            return None

        if len(parts) == 1:
            return "", deserialize_json(parts[0])

        topic = parts[0].decode("utf-8", errors="replace")
        data = deserialize_json(parts[1])
        return topic, data

    def close(self) -> None:
        """Close subscriber socket and context if owned."""
        if self.socket and not self.socket.closed:
            self.socket.close(linger=0)
        if self._owned_context and self.context and not self.context.closed:
            self.context.term()

    def __enter__(self) -> ZMQSubscriber:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# ---------------------------------------------------------------------------
# ZMQ Req Client (Lazy Pirate Pattern)
# ---------------------------------------------------------------------------


class ZMQReqClient:
    """
    ZeroMQ Request Client implementing the Lazy Pirate Pattern:
    - Sets timeout on response
    - On timeout, safely closes and recreates socket
    - Retries request up to configured retry limit with retry_delay_ms backoff
    - Gracefully handles server restarts and network drops
    """

    def __init__(
        self,
        endpoint: str,
        timeout_ms: int = 1000,
        retries: int = 3,
        retry_delay_ms: int = 50,
        context: zmq.Context | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_ms = timeout_ms
        self.retries = retries
        self.retry_delay_ms = retry_delay_ms
        self._owned_context = False
        self.context = context or zmq.Context.instance()
        self.socket: zmq.Socket | None = None
        self._poller = zmq.Poller()
        self._lock = threading.Lock()
        self._init_socket()

    def _init_socket(self) -> None:
        """Initialize or re-initialize REQ socket."""
        if self.socket is not None and not self.socket.closed:
            try:
                self._poller.unregister(self.socket)
            except Exception:
                pass
            self.socket.close(linger=0)

        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.LINGER, 0)
        try:
            self.socket.setsockopt(zmq.REQ_RELAXED, 1)
            self.socket.setsockopt(zmq.REQ_CORRELATE, 1)
        except AttributeError:
            pass  # older pyzmq versions

        self.socket.connect(self.endpoint)
        self._poller.register(self.socket, zmq.POLLIN)

    def send_request(
        self,
        payload: dict[str, Any] | str | bytes,
        timeout_ms: int | None = None,
        retries: int | None = None,
    ) -> bytes | None:
        """
        Send request and receive reply using Lazy Pirate pattern.
        Returns reply raw bytes, or None if all retries timed out.
        """
        with self._lock:
            t_ms = timeout_ms if timeout_ms is not None else self.timeout_ms
            max_retries = retries if retries is not None else self.retries

            if isinstance(payload, bytes):
                wire_data = payload
            elif isinstance(payload, str):
                wire_data = payload.encode("utf-8")
            elif isinstance(payload, (dict, list)):
                wire_data = serialize_json(payload)
            else:
                wire_data = str(payload).encode("utf-8")

            for attempt in range(1, max_retries + 1):
                try:
                    if self.socket is None or self.socket.closed:
                        self._init_socket()

                    assert self.socket is not None
                    self.socket.send(wire_data)

                    # Poll for reply
                    socks = dict(self._poller.poll(t_ms))
                    if self.socket in socks:
                        reply = self.socket.recv()
                        return reply

                    # Timeout occurred -> Lazy Pirate reconnection
                    logger.warning(
                        f"ZMQReqClient request timeout ({t_ms}ms) on {self.endpoint} "
                        f"[Attempt {attempt}/{max_retries}]. Reconnecting socket..."
                    )
                    self._init_socket()
                    if self.retry_delay_ms > 0:
                        time.sleep(self.retry_delay_ms / 1000.0)

                except zmq.ZMQError as e:
                    logger.warning(f"ZMQReqClient error on attempt {attempt}: {e}")
                    self._init_socket()
                except Exception as e:
                    logger.error(f"Unexpected error in ZMQReqClient: {e}")
                    self._init_socket()

            logger.error(f"ZMQReqClient failed to get reply after {max_retries} attempts.")
            return None

    def request_json(
        self,
        data: dict[str, Any] | list[Any],
        timeout_ms: int | None = None,
        retries: int | None = None,
    ) -> Any | None:
        """
        Send JSON request and receive deserialized JSON reply.
        Returns parsed JSON object or None on failure/timeout.
        """
        reply_bytes = self.send_request(data, timeout_ms=timeout_ms, retries=retries)
        if reply_bytes is None:
            return None
        return deserialize_json(reply_bytes)

    def close(self) -> None:
        """Close REQ socket and context if owned."""
        with self._lock:
            if self.socket and not self.socket.closed:
                self.socket.close(linger=0)
            if self._owned_context and self.context and not self.context.closed:
                self.context.term()

    def __enter__(self) -> ZMQReqClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# ---------------------------------------------------------------------------
# ZMQ Rep Server
# ---------------------------------------------------------------------------


class ZMQRepServer:
    """
    ZeroMQ Reply Server for RPC / inter-brain command requests.
    """

    def __init__(
        self,
        endpoint: str,
        bind: bool = True,
        rcvtimeo_ms: int | None = None,
        context: zmq.Context | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.bind_mode = bind
        self._owned_context = False
        self.context = context or zmq.Context.instance()
        self.socket = self.context.socket(zmq.REP)
        self.socket.setsockopt(zmq.LINGER, 0)

        if rcvtimeo_ms is not None and rcvtimeo_ms >= 0:
            self.socket.setsockopt(zmq.RCVTIMEO, rcvtimeo_ms)

        if self.bind_mode:
            self.socket.bind(self.endpoint)
            logger.info(f"ZMQRepServer bound to {self.endpoint}")
        else:
            self.socket.connect(self.endpoint)
            logger.info(f"ZMQRepServer connected to {self.endpoint}")

        self._poller = zmq.Poller()
        self._poller.register(self.socket, zmq.POLLIN)

    def recv_request(
        self,
        flags: int = 0,
        timeout_ms: int | None = None,
    ) -> bytes | None:
        """
        Receive request raw bytes.
        Returns bytes or None on timeout/EAGAIN.
        """
        try:
            if timeout_ms is not None:
                socks = dict(self._poller.poll(timeout_ms))
                if self.socket not in socks:
                    return None

            return self.socket.recv(flags=flags)
        except zmq.Again:
            return None
        except zmq.ZMQError as e:
            logger.warning(f"RepServer ZMQError on {self.endpoint}: {e}")
            return None

    def recv_json(
        self,
        flags: int = 0,
        timeout_ms: int | None = None,
    ) -> Any | None:
        """
        Receive and deserialize JSON request.
        Returns parsed JSON object or None on failure/timeout.
        """
        raw = self.recv_request(flags=flags, timeout_ms=timeout_ms)
        if raw is None:
            return None
        return deserialize_json(raw)

    def send_reply(
        self,
        payload: dict[str, Any] | list[Any] | str | bytes,
        flags: int = 0,
    ) -> bool:
        """
        Send reply to current pending request.
        Returns True on success, False on error.
        """
        try:
            if isinstance(payload, bytes):
                data = payload
            elif isinstance(payload, str):
                data = payload.encode("utf-8")
            elif isinstance(payload, (dict, list)):
                data = serialize_json(payload)
            else:
                data = str(payload).encode("utf-8")

            self.socket.send(data, flags=flags)
            return True
        except zmq.ZMQError as e:
            logger.warning(f"RepServer reply ZMQError on {self.endpoint}: {e}")
            return False

    def send_json(self, data: Any, flags: int = 0) -> bool:
        """Send JSON reply."""
        return self.send_reply(data, flags=flags)

    def close(self) -> None:
        """Close REP socket and context if owned."""
        if self.socket and not self.socket.closed:
            self.socket.close(linger=0)
        if self._owned_context and self.context and not self.context.closed:
            self.context.term()

    def __enter__(self) -> ZMQRepServer:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
