from __future__ import annotations

from dataclasses import dataclass
from ftplib import FTP, FTP_TLS
from io import BytesIO
from typing import Iterable


@dataclass
class FtpLogClient:
    host: str
    username: str
    password: str
    remote_path: str
    port: int = 21
    use_tls: bool = False
    timeout_seconds: int = 30

    def download(self) -> bytes:
        buffer = BytesIO()
        with self._connect() as ftp:
            ftp.retrbinary(f"RETR {self.remote_path}", buffer.write)

        return buffer.getvalue()

    def find_files(
        self,
        filename: str,
        start_path: str = "/",
        max_depth: int = 8,
        max_entries: int = 5000,
    ) -> list[str]:
        results: list[str] = []
        seen_dirs: set[str] = set()
        visited_entries = 0

        with self._connect() as ftp:
            original_dir = _safe_pwd(ftp)

            def walk(path: str, depth: int) -> None:
                nonlocal visited_entries
                if depth < 0 or visited_entries >= max_entries:
                    return

                normalized_path = _normalize_remote_path(path)
                if normalized_path in seen_dirs:
                    return
                seen_dirs.add(normalized_path)

                for entry in _iter_entries(ftp, normalized_path):
                    if visited_entries >= max_entries:
                        return
                    visited_entries += 1

                    name = entry.name
                    if name in {".", ".."}:
                        continue

                    child_path = _remote_join(normalized_path, name)
                    if name == filename:
                        results.append(child_path)

                    if entry.is_dir:
                        walk(child_path, depth - 1)

            walk(start_path, max_depth)
            if original_dir:
                try:
                    ftp.cwd(original_dir)
                except OSError:
                    pass

        return sorted(dict.fromkeys(results))

    def _connect(self) -> FTP:
        ftp_class = FTP_TLS if self.use_tls else FTP

        ftp = ftp_class()
        ftp.connect(self.host, self.port, timeout=self.timeout_seconds)
        ftp.login(self.username, self.password)
        if isinstance(ftp, FTP_TLS):
            ftp.prot_p()
        ftp.set_pasv(True)
        return ftp


@dataclass
class FtpEntry:
    name: str
    is_dir: bool


def _iter_entries(ftp: FTP, path: str) -> Iterable[FtpEntry]:
    try:
        for name, facts in ftp.mlsd(path):
            kind = facts.get("type", "").casefold()
            yield FtpEntry(name=name, is_dir=kind in {"dir", "cdir", "pdir"})
        return
    except OSError:
        pass

    try:
        names = ftp.nlst(path)
    except OSError:
        return

    current_dir = _safe_pwd(ftp)
    for raw_name in names:
        name = raw_name.rsplit("/", 1)[-1]
        if name in {".", ".."}:
            continue
        child_path = raw_name if raw_name.startswith("/") else _remote_join(path, name)
        is_dir = False
        try:
            ftp.cwd(child_path)
            is_dir = True
        except OSError:
            is_dir = False
        finally:
            if current_dir:
                try:
                    ftp.cwd(current_dir)
                except OSError:
                    pass
        yield FtpEntry(name=name, is_dir=is_dir)


def _safe_pwd(ftp: FTP) -> str | None:
    try:
        return ftp.pwd()
    except OSError:
        return None


def _normalize_remote_path(path: str) -> str:
    stripped = path.strip() or "/"
    if stripped == ".":
        return "."
    if stripped != "/" and stripped.endswith("/"):
        return stripped.rstrip("/")
    return stripped


def _remote_join(base: str, name: str) -> str:
    if base in {"", "."}:
        return name
    if base == "/":
        return "/" + name.lstrip("/")
    return base.rstrip("/") + "/" + name.lstrip("/")
