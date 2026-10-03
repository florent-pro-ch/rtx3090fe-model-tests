#!/usr/bin/env python3
"""G2 — generic leak scan of the public tree (and of the built site).

Looks for the shapes of things that must never be published, with generic patterns
only (no private literal lives in this file):

  private IPv4 (RFC 1918, the 100.64/10 shared/CGNAT range, 169.254/16 link-local),
  private IPv6 (fe80::/10 link-local, fc00::/7 unique-local), MAC addresses, home
  directories (home/<user>, Users/<user>, the root home), ssh or scp targets (a user
  at a host), a user at an IP address,
  API tokens (OpenAI/Anthropic-style sk-, Hugging Face hf_, GitHub ghp_/github_pat_,
  AWS AKIA/ASIA, Slack xox*-, Google AIza, JWTs, long Bearer tokens), private key
  blocks, secret-bearing file names (.env, id_rsa, *.pem, *.key...), and e-mail
  addresses outside the domains listed in tools/email-allowlist.txt.

Findings are printed masked (CI logs of a public repo are public). Reviewed false
positives go in tools/exceptions.json ({"tool": "scan_public", "file": <glob>,
"rule": <rule>, "reason": <why>}).

usage:
  tools/scan_public.py              # the whole repo (site/dist included when built)
  tools/scan_public.py site/dist    # only the built site
  tools/scan_public.py --list-rules
Exit status: 0 clean, 1 findings, 2 usage error.
"""
from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gatelib import REPO, excepted, iter_files, lines_of, load_exceptions, mask, rel  # noqa: E402

# (first octets, prefix length) — written as tuples so this file never matches itself
_V4 = [((10, 0, 0, 0), 8), ((172, 16, 0, 0), 12), ((192, 168, 0, 0), 16),
       ((100, 64, 0, 0), 10), ((169, 254, 0, 0), 16)]
PRIVATE_V4 = [ipaddress.ip_network((".".join(map(str, o)), n)) for o, n in _V4]
FILE_EXT_TLDS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "avif", "ico", "css", "js", "mjs",
                 "ts", "json", "md", "html", "woff", "woff2", "ttf", "map"}
SECRET_FILES = re.compile(r"^(?:\.env(?:\.(?!example$|sample$|template$)[\w.-]+)?|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?"
                          r"|.*\.(?:pem|key|p12|pfx|jks|keystore|ovpn)|\.netrc|\.pgpass|credentials(?:\.json)?"
                          r"|.*\.tfstate(?:\.backup)?)$", re.I)

RX = {
    "ipv4-private": re.compile(r"(?<![\w.@~^])(?<!==)(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?![\w.]*\d)"),
    "ipv6-private": re.compile(r"(?i)(?<![\w:.])(?:fe[89ab][0-9a-f]|f[cd][0-9a-f]{2}):(?::?[0-9a-f]{1,4}){1,7}(?![\w:])"),
    "mac-address": re.compile(r"(?i)(?<![\w:-])[0-9a-f]{2}([:-])(?:[0-9a-f]{2}\1){4}[0-9a-f]{2}(?![\w:-])"),
    "home-path": re.compile(r"(?<![\w.~])/home/(?!runner\b)[A-Za-z0-9_.-]+"),
    "users-path": re.compile(r"(?<![\w.])/(?:Users)/[A-Za-z0-9_.-]+"),
    "root-path": re.compile(r"(?<![\w.~])/(?:root)/"),
    "ssh-target": re.compile(r"\b(?:ssh|scp|sftp|rsync)\b[^\n|`\"']{0,60}?\b([A-Za-z_][A-Za-z0-9_.-]*)@([A-Za-z0-9][A-Za-z0-9_.-]*)"),
    "user-at-ip": re.compile(r"\b[A-Za-z_][A-Za-z0-9_.-]*@(?:\d{1,3}\.){3}\d{1,3}\b"),
    "token-sk": re.compile(r"\bsk-(?:proj-|ant-|svcacct-|or-)?[A-Za-z0-9_-]{20,}"),
    "token-hf": re.compile(r"\bhf_[A-Za-z0-9]{20,}"),
    "token-github": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{22,}"),
    "token-aws": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "token-slack": re.compile(r"\bxox[abeprs]-[A-Za-z0-9-]{10,}"),
    "token-google": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "token-jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "token-bearer": re.compile(r"(?i)\bbearer\s+(?!<)[A-Za-z0-9._~+/=-]{24,}"),
    "private-key": re.compile(r"-{5}BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-{5}"),
    "email": re.compile(r"(?<![\w.+%-])[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})\b"),
}
RULES = sorted(list(RX) + ["secret-file"])


def load_email_allowlist(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            out.add(line.lstrip("@"))
    return out


def domain_allowed(domain: str, allow: set[str]) -> bool:
    d = domain.lower()
    return any(d == a or d.endswith("." + a) for a in allow)


def findings_in_line(line: str, allow: set[str]):
    for rule, rx in RX.items():
        for m in rx.finditer(line):
            text = m.group(0)
            if rule == "ipv4-private":
                parts = m.group(1).split(".")
                if any(len(p) > 1 and p.startswith("0") for p in parts):
                    continue  # version strings such as 94.02.27.00
                try:
                    ip = ipaddress.ip_address(m.group(1))
                except ValueError:
                    continue
                if not any(ip in n for n in PRIVATE_V4):
                    continue
            elif rule == "mac-address":
                if len(set(re.sub(r"[:-]", "", text.lower()))) == 1:
                    continue  # 00:00:00:00:00:00, ff:ff:...
            elif rule == "ssh-target":
                user, host = m.group(1), m.group(2).lower()
                if user == "git" and host in ("github.com", "gitlab.com", "codeberg.org"):
                    continue
                if domain_allowed(host, allow):
                    continue
            elif rule == "email":
                domain = m.group(1)
                if domain.rsplit(".", 1)[-1].lower() in FILE_EXT_TLDS or domain_allowed(domain, allow):
                    continue
            yield rule, text


def scan(paths: list[Path], allow: set[str], exceptions: list[dict]):
    found, skipped = [], Counter()
    nfiles = 0
    for base in paths:
        files = [base] if base.is_file() else iter_files(base)
        for f in files:
            nfiles += 1
            r = rel(f)
            if SECRET_FILES.match(f.name) and not excepted(exceptions, r, "secret-file"):
                found.append((r, 0, "secret-file", f.name))
            try:
                for n, line in lines_of(f):
                    for rule, text in findings_in_line(line, allow):
                        if excepted(exceptions, r, rule):
                            skipped[rule] += 1
                            continue
                        found.append((r, n, rule, text))
            except OSError as exc:
                found.append((r, 0, "unreadable", type(exc).__name__))
    return nfiles, found, skipped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 epilog="Exit status: 0 clean, 1 findings, 2 usage error.")
    ap.add_argument("paths", nargs="*", help="files or directories to scan (default: the whole repo)")
    ap.add_argument("--allowlist", default=str(REPO / "tools" / "email-allowlist.txt"),
                    help="e-mail domains that may appear (default: tools/email-allowlist.txt)")
    ap.add_argument("--list-rules", action="store_true", help="print the rule names and exit")
    args = ap.parse_args(argv)
    if args.list_rules:
        print("\n".join(RULES))
        return 0
    paths = [Path(p) if Path(p).is_absolute() else Path.cwd() / p for p in args.paths] or [REPO]
    for p in paths:
        if not p.exists():
            print(f"scan_public: no such path: {p}", file=sys.stderr)
            return 2
    allow = load_email_allowlist(Path(args.allowlist))
    exceptions, exc_errors = load_exceptions("scan_public")
    nfiles, found, skipped = scan(paths, allow, exceptions)
    for e in exc_errors:
        print(f"EXCEPTION ERROR  {e}")
    for r, n, rule, text in found:
        print(f"LEAK  {r}:{n if n else '-'}  {rule}  {mask(text)}")
    by_rule = Counter(rule for _, _, rule, _ in found)
    print(f"scan_public: {nfiles} files, {len(found)} finding(s)"
          + (f" {dict(sorted(by_rule.items()))}" if found else "")
          + (f", {sum(skipped.values())} excepted" if skipped else ""))
    return 1 if found or exc_errors else 0


if __name__ == "__main__":
    sys.exit(main())
