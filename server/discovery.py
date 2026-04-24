from __future__ import annotations

import socket

from zeroconf import IPVersion, ServiceInfo, Zeroconf


SERVICE_TYPE = "_sussurro._tcp.local."


def _best_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 53))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


class MdnsBroadcaster:
    def __init__(self, port: int, name: str | None = None) -> None:
        self.port = port
        hostname = socket.gethostname().split(".")[0]
        self.name = name or f"Sussurro on {hostname}"
        self._zc: Zeroconf | None = None
        self._info: ServiceInfo | None = None

    def start(self) -> None:
        ip = _best_local_ip()
        self._zc = Zeroconf(ip_version=IPVersion.V4Only)
        service_name = f"{self.name}.{SERVICE_TYPE}"
        self._info = ServiceInfo(
            SERVICE_TYPE,
            service_name,
            addresses=[socket.inet_aton(ip)],
            port=self.port,
            properties={"path": "/", "version": "1"},
            server=f"{socket.gethostname()}.local.",
        )
        self._zc.register_service(self._info)
        print(f"[mdns] advertised '{service_name}' at {ip}:{self.port}")

    def stop(self) -> None:
        if self._zc is not None and self._info is not None:
            try:
                self._zc.unregister_service(self._info)
            except Exception:  # noqa: BLE001
                pass
            self._zc.close()
        self._zc = None
        self._info = None
