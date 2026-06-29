"""Security analyzer.

A small, regex/AST-based linter for the kinds of issues that show up
in real-world Python projects:

* hard-coded secrets (API keys, tokens, passwords);
* unsafe calls to :func:`os.system`, :func:`subprocess.Popen` with
  ``shell=True``, or :func:`eval`/:func:`exec`;
* ``pickle.load`` on untrusted data;
* weak hashing (``md5``, ``sha1``) for security-sensitive use;
* ``assert`` statements in production code (stripped by ``python -O``).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import ClassVar

from forgecli.review.analyzer import AnalysisContext, Analyzer
from forgecli.review.finding import Finding, Severity

_SECRET_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "SEC001",
        "AWS access key id",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
    (
        "SEC002",
        "Generic API key assignment",
        re.compile(
            r"(?i)(?:api[_-]?key|secret|token|password|passwd|pwd)"
            r"\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"
        ),
    ),
    (
        "SEC003",
        "PEM private key block",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "SEC004",
        "Slack/bot token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ),
)


_UNSAFE_CALLS: tuple[tuple[str, str, str], ...] = (
    # (qualified-prefix-or-None, attr-or-None, rule_id)
    # Module-qualified calls.
    ("os", "system", "SEC010"),
    ("os", "popen", "SEC011"),
    ("subprocess", "call", "SEC012"),
    ("subprocess", "Popen", "SEC013"),
    ("pickle", "load", "SEC017"),
    ("pickle", "loads", "SEC018"),
    ("marshal", "load", "SEC019"),
    ("marshal", "loads", "SEC020"),
    # Builtins (no qualifier).
    (None, "eval", "SEC014"),
    (None, "exec", "SEC015"),
    (None, "compile", "SEC016"),
)


_WEAK_HASH_NAMES: frozenset[str] = frozenset({"md5", "sha1"})


@dataclass
class SecurityAnalyzer(Analyzer):
    """Find hard-coded secrets and unsafe calls."""

    name: ClassVar[str] = "security"
    category: ClassVar[str] = "security"
    _EXTRA_RULES: ClassVar[tuple[tuple[str, str, re.Pattern[str]], ...]] = ()

    def run(self, context: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        for file in context.files:
            findings.extend(self._scan_secrets(file))
            findings.extend(self._scan_unsafe_calls(file))
            findings.extend(self._scan_weak_hash(file))
            findings.extend(self._scan_asserts(file))
        return findings

    def _scan_secrets(self, file) -> list[Finding]:
        out: list[Finding] = []
        for index, line in enumerate(file.lines, start=1):
            for rule_id, label, pattern in _SECRET_PATTERNS:
                if pattern.search(line):
                    out.append(
                        Finding(
                            rule_id=rule_id,
                            category="security",
                            severity=Severity.CRITICAL,
                            message=f"Possible hard-coded {label}.",
                            path=str(file.path),
                            line=index,
                            suggestion=(
                                "Move the secret to an environment variable "
                                "or a secret manager."
                            ),
                        )
                    )
        return out

    def _scan_unsafe_calls(self, file) -> list[Finding]:
        out: list[Finding] = []
        try:
            tree = ast.parse(file.text)
        except SyntaxError:
            return out
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            qualified = _qualified_name(node.func)
            if qualified is None:
                continue
            for module, attr, rule_id in _UNSAFE_CALLS:
                target = f"{module}.{attr}" if module else attr
                if qualified != target:
                    continue
                out.append(
                    Finding(
                        rule_id=rule_id,
                        category="security",
                        severity=Severity.HIGH,
                        message=f"Unsafe call to {qualified}().",
                        path=str(file.path),
                        line=node.lineno,
                        suggestion=_suggest_for(rule_id),
                    )
                )
            if qualified in {"subprocess.call", "subprocess.Popen"} and any(
                isinstance(kw.value, ast.Constant)
                and kw.value.value is True
                for kw in node.keywords
                if kw.arg == "shell"
            ):
                out.append(
                    Finding(
                        rule_id="SEC013",
                        category="security",
                        severity=Severity.CRITICAL,
                        message=(
                            f"{qualified}(shell=True) is vulnerable to command injection."
                        ),
                        path=str(file.path),
                        line=node.lineno,
                        suggestion=(
                            "Pass a list of arguments and drop shell=True; "
                            "use shlex.quote() only on fully-trusted input."
                        ),
                    )
                )
        return out

    def _scan_weak_hash(self, file) -> list[Finding]:
        out: list[Finding] = []
        try:
            tree = ast.parse(file.text)
        except SyntaxError:
            return out
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _qualified_name(node.func)
            if name is None:
                continue
            short = name.rsplit(".", 1)[-1]
            if short in _WEAK_HASH_NAMES:
                out.append(
                    Finding(
                        rule_id="SEC021",
                        category="security",
                        severity=Severity.MEDIUM,
                        message=(
                            f"{name} is a weak hash; prefer sha256 or sha3_256."
                        ),
                        path=str(file.path),
                        line=node.lineno,
                        suggestion=(
                            "Use hashlib.sha256() (or stronger) for any "
                            "security-sensitive use."
                        ),
                    )
                )
        return out

    def _scan_asserts(self, file) -> list[Finding]:
        out: list[Finding] = []
        try:
            tree = ast.parse(file.text)
        except SyntaxError:
            return out
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue
            out.append(
                Finding(
                    rule_id="SEC022",
                    category="security",
                    severity=Severity.LOW,
                    message=(
                        "assert statement is removed under `python -O`; "
                        "don't use it for runtime checks."
                    ),
                    path=str(file.path),
                    line=node.lineno,
                    suggestion="Raise an explicit exception instead.",
                )
            )
        return out


def _qualified_name(node: ast.AST) -> str | None:
    """Return the dotted name for a callable node, or None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _qualified_name(node.value)
        if base is None:
            return None
        return f"{base}.{node.attr}"
    return None


def _suggest_for(rule_id: str) -> str:
    return {
        "SEC010": "Use subprocess.run([...], shell=False) instead of os.system.",
        "SEC011": "Use subprocess.run([...], shell=False) instead of os.popen.",
        "SEC012": "Pass a list of arguments and shell=False to subprocess.call.",
        "SEC013": "Pass a list of arguments and shell=False to subprocess.Popen.",
        "SEC014": "Avoid eval(); use ast.literal_eval() or explicit parsing.",
        "SEC015": "Avoid exec() on dynamic input; it's a remote-code vector.",
        "SEC016": "Avoid compile() on user input.",
        "SEC017": "Use json or a safe deserializer; pickle is unsafe on untrusted data.",
        "SEC018": "Use json or a safe deserializer; pickle is unsafe on untrusted data.",
        "SEC019": "marshal is not a safe deserialization format for untrusted data.",
        "SEC020": "marshal is not a safe deserialization format for untrusted data.",
    }.get(rule_id, "Replace with a safer alternative.")


__all__ = ["SecurityAnalyzer"]


# Silence unused-import warnings for symbols only used in some branches.
_ = field
