"""Shell-substitution body extractors.

Mirrors scripts/lib/shell-substitution.js from affaan-m/everything-claude-code
@ 4774946d. Returns bodies stripped of their surrounding delimiters; quote-awareness
matches bash semantics (single quotes opaque, double quotes transparent for $() and
backticks).

Provides three main extractors:
- extract_command_substitutions: finds $(...) and `...` bodies (recursive)
- extract_subshell_groups: finds plain (...) subshells
- extract_brace_groups: finds { ...; } brace groups (recursive)

All functions handle nested quotes, escaped characters, and proper depth tracking
to support the gateguard PreToolUse hook's safe-bash detection.
"""
from __future__ import annotations


def extract_command_substitutions(text: str) -> list[str]:
    """Extract bodies of $(...) and `...` outside single quotes.

    Single quotes are literal (bash doesn't expand inside them).
    Double quotes are transparent to $() and backticks.
    Returns all top-level and nested substitution bodies.

    Args:
        text: Shell command line to scan

    Returns:
        List of command substitution bodies (stripped of $( ) or ` `)
    """
    source = str(text or "")
    substitutions: list[str] = []
    i = 0
    in_single = False
    in_double = False

    while i < len(source):
        ch = source[i]
        prev = source[i - 1] if i > 0 else ""

        # Handle escapes (outside single quotes)
        if ch == "\\" and not in_single:
            i += 2
            continue

        # Toggle single quote state
        if ch == "'" and not in_double and prev != "\\":
            in_single = not in_single
            i += 1
            continue

        # Toggle double quote state
        if ch == '"' and not in_single and prev != "\\":
            in_double = not in_double
            i += 1
            continue

        # Inside single quotes, everything is literal
        if in_single:
            i += 1
            continue

        # Handle backticks
        if ch == "`":
            body = ""
            i += 1
            while i < len(source):
                inner = source[i]
                if inner == "\\":
                    body += inner
                    if i + 1 < len(source):
                        body += source[i + 1]
                        i += 2
                        continue
                if inner == "`":
                    break
                body += inner
                i += 1

            if body.strip():
                substitutions.append(body)
                # Recurse to find nested substitutions
                substitutions.extend(extract_command_substitutions(body))
            continue

        # Handle $(...) command substitution
        if ch == "$" and i + 1 < len(source) and source[i + 1] == "(":
            depth = 1
            body = ""
            body_in_single = False
            body_in_double = False
            i += 2

            while i < len(source) and depth > 0:
                inner = source[i]
                inner_prev = source[i - 1] if i > 0 else ""

                # Handle escapes in body (outside single quotes)
                if inner == "\\" and not body_in_single:
                    body += inner
                    if i + 1 < len(source):
                        body += source[i + 1]
                        i += 2
                        continue

                # Toggle quote states in body
                if inner == "'" and not body_in_double and inner_prev != "\\":
                    body_in_single = not body_in_single
                elif inner == '"' and not body_in_single and inner_prev != "\\":
                    body_in_double = not body_in_double
                elif not body_in_single and not body_in_double:
                    # Track parenthesis depth when not in quotes
                    if inner == "(":
                        depth += 1
                    elif inner == ")":
                        depth -= 1
                        if depth == 0:
                            break

                body += inner
                i += 1

            if body.strip():
                substitutions.append(body)
                # Recurse to find nested substitutions
                substitutions.extend(extract_command_substitutions(body))
            continue

        i += 1

    return substitutions


def extract_subshell_groups(text: str) -> list[str]:
    """Extract bodies of plain (...) subshells (not $(...)).

    Distinguishes from $(...)  command substitutions and backticks.
    Single quotes are literal. Double quotes are literal for plain parens
    (bash only honors $(...) inside double quotes, not bare (...)).

    Args:
        text: Shell command line to scan

    Returns:
        List of subshell group bodies (stripped of ( ))
    """
    source = str(text or "")
    groups: list[str] = []
    i = 0
    in_single = False
    in_double = False

    while i < len(source):
        ch = source[i]
        prev = source[i - 1] if i > 0 else ""

        # Handle escapes (outside single quotes)
        if ch == "\\" and not in_single:
            i += 2
            continue

        # Toggle single quote state
        if ch == "'" and not in_double and prev != "\\":
            in_single = not in_single
            i += 1
            continue

        # Toggle double quote state
        if ch == '"' and not in_single and prev != "\\":
            in_double = not in_double
            i += 1
            continue

        # Inside quotes, skip
        if in_single or in_double:
            i += 1
            continue

        # Skip $(...) — already handled by extract_command_substitutions
        if ch == "$" and i + 1 < len(source) and source[i + 1] == "(":
            depth = 1
            skip_in_single = False
            skip_in_double = False
            i += 2

            while i < len(source) and depth > 0:
                inner = source[i]
                inner_prev = source[i - 1] if i > 0 else ""

                if inner == "\\" and not skip_in_single:
                    i += 2
                    continue

                if inner == "'" and not skip_in_double and inner_prev != "\\":
                    skip_in_single = not skip_in_single
                elif inner == '"' and not skip_in_single and inner_prev != "\\":
                    skip_in_double = not skip_in_double
                elif not skip_in_single and not skip_in_double:
                    if inner == "(":
                        depth += 1
                    elif inner == ")":
                        depth -= 1

                i += 1

            continue

        # Skip backticks — already handled by extract_command_substitutions
        if ch == "`":
            i += 1
            while i < len(source) and source[i] != "`":
                if source[i] == "\\" and i + 1 < len(source):
                    i += 2
                    continue
                i += 1
            if i < len(source):
                i += 1
            continue

        # Handle plain (...) subshell
        if ch == "(":
            depth = 1
            body = ""
            body_in_single = False
            body_in_double = False
            i += 1

            while i < len(source) and depth > 0:
                inner = source[i]
                inner_prev = source[i - 1] if i > 0 else ""

                # Handle escapes in body (outside single quotes)
                if inner == "\\" and not body_in_single:
                    body += inner
                    if i + 1 < len(source):
                        body += source[i + 1]
                        i += 2
                        continue

                # Toggle quote states in body
                if inner == "'" and not body_in_double and inner_prev != "\\":
                    body_in_single = not body_in_single
                elif inner == '"' and not body_in_single and inner_prev != "\\":
                    body_in_double = not body_in_double
                elif not body_in_single and not body_in_double:
                    # Track parenthesis depth when not in quotes
                    if inner == "(":
                        depth += 1
                    elif inner == ")":
                        depth -= 1
                        if depth == 0:
                            break

                body += inner
                i += 1

            if body.strip():
                groups.append(body)
                # Recurse to find nested subshells
                groups.extend(extract_subshell_groups(body))
            continue

        i += 1

    return groups


def extract_brace_groups(text: str) -> list[str]:
    """Extract bodies of { ...; } brace groups.

    Bash brace groups run in the current shell (unlike (...) which fork).
    Recognition rules match bash's reserved-word semantics:
    - `{` is reserved only when followed by whitespace and preceded by
      line start, whitespace, or shell operator (;, |, &, ().
    - `}` closes only when preceded by ; or whitespace.
    - Single and double quotes are literal for brace recognition.
    - Nested $(...), backticks, and (...) spans are skipped.

    Args:
        text: Shell command line to scan

    Returns:
        List of brace group bodies (stripped of { and })
    """
    source = str(text or "")
    groups: list[str] = []
    i = 0
    in_single = False
    in_double = False

    while i < len(source):
        ch = source[i]
        prev = source[i - 1] if i > 0 else ""

        # Handle escapes (outside single quotes)
        if ch == "\\" and not in_single:
            i += 2
            continue

        # Toggle single quote state
        if ch == "'" and not in_double and prev != "\\":
            in_single = not in_single
            i += 1
            continue

        # Toggle double quote state
        if ch == '"' and not in_single and prev != "\\":
            in_double = not in_double
            i += 1
            continue

        # Inside quotes, skip
        if in_single or in_double:
            i += 1
            continue

        # Skip $(...) — already handled by extract_command_substitutions
        if ch == "$" and i + 1 < len(source) and source[i + 1] == "(":
            depth = 1
            skip_in_single = False
            skip_in_double = False
            i += 2

            while i < len(source) and depth > 0:
                inner = source[i]
                inner_prev = source[i - 1] if i > 0 else ""

                if inner == "\\" and not skip_in_single:
                    i += 2
                    continue

                if inner == "'" and not skip_in_double and inner_prev != "\\":
                    skip_in_single = not skip_in_single
                elif inner == '"' and not skip_in_single and inner_prev != "\\":
                    skip_in_double = not skip_in_double
                elif not skip_in_single and not skip_in_double:
                    if inner == "(":
                        depth += 1
                    elif inner == ")":
                        depth -= 1

                i += 1

            continue

        # Skip backticks — already handled by extract_command_substitutions
        if ch == "`":
            i += 1
            while i < len(source) and source[i] != "`":
                if source[i] == "\\" and i + 1 < len(source):
                    i += 2
                    continue
                i += 1
            if i < len(source):
                i += 1
            continue

        # Skip plain (...) subshells — already handled by extract_subshell_groups
        if ch == "(":
            depth = 1
            skip_in_single = False
            skip_in_double = False
            i += 1

            while i < len(source) and depth > 0:
                inner = source[i]
                inner_prev = source[i - 1] if i > 0 else ""

                if inner == "\\" and not skip_in_single:
                    i += 2
                    continue

                if inner == "'" and not skip_in_double and inner_prev != "\\":
                    skip_in_single = not skip_in_single
                elif inner == '"' and not skip_in_single and inner_prev != "\\":
                    skip_in_double = not skip_in_double
                elif not skip_in_single and not skip_in_double:
                    if inner == "(":
                        depth += 1
                    elif inner == ")":
                        depth -= 1

                i += 1

            continue

        # Handle { ...; } brace group
        # `{` is reserved only when followed by whitespace
        if ch == "{" and i + 1 < len(source) and source[i + 1].isspace():
            # Check if prev is a boundary (line start, whitespace, or operator)
            prev_is_boundary = (
                i == 0 or prev in " \t\n\r;|&("
            )
            if not prev_is_boundary:
                i += 1
                continue

            depth = 1
            body = ""
            body_in_single = False
            body_in_double = False
            i += 1

            while i < len(source) and depth > 0:
                inner = source[i]
                inner_prev = source[i - 1] if i > 0 else ""

                # Handle escapes in body (outside single quotes)
                if inner == "\\" and not body_in_single:
                    body += inner
                    if i + 1 < len(source):
                        body += source[i + 1]
                        i += 2
                        continue

                # Toggle single quote state
                if inner == "'" and not body_in_double and inner_prev != "\\":
                    body_in_single = not body_in_single
                    body += inner
                    i += 1
                    continue

                # Toggle double quote state
                if inner == '"' and not body_in_single and inner_prev != "\\":
                    body_in_double = not body_in_double
                    body += inner
                    i += 1
                    continue

                # Inside quotes, just accumulate
                if body_in_single or body_in_double:
                    body += inner
                    i += 1
                    continue

                # Skip $(...) spans inside brace body
                if inner == "$" and i + 1 < len(source) and source[i + 1] == "(":
                    body += inner + source[i + 1]
                    sub_depth = 1
                    sub_in_single = False
                    sub_in_double = False
                    i += 2

                    while i < len(source) and sub_depth > 0:
                        c = source[i]
                        p = source[i - 1] if i > 0 else ""
                        body += c

                        if c == "\\" and not sub_in_single and i + 1 < len(source):
                            body += source[i + 1]
                            i += 2
                            continue

                        if c == "'" and not sub_in_double and p != "\\":
                            sub_in_single = not sub_in_single
                        elif c == '"' and not sub_in_single and p != "\\":
                            sub_in_double = not sub_in_double
                        elif not sub_in_single and not sub_in_double:
                            if c == "(":
                                sub_depth += 1
                            elif c == ")":
                                sub_depth -= 1

                        i += 1

                    continue

                # Skip backtick spans inside brace body
                if inner == "`":
                    body += inner
                    i += 1

                    while i < len(source) and source[i] != "`":
                        if source[i] == "\\" and i + 1 < len(source):
                            body += source[i] + source[i + 1]
                            i += 2
                            continue
                        body += source[i]
                        i += 1

                    if i < len(source):
                        body += source[i]
                        i += 1

                    continue

                # Skip plain (...) subshells inside brace body
                if inner == "(":
                    body += inner
                    sub_depth = 1
                    sub_in_single = False
                    sub_in_double = False
                    i += 1

                    while i < len(source) and sub_depth > 0:
                        c = source[i]
                        p = source[i - 1] if i > 0 else ""
                        body += c

                        if c == "\\" and not sub_in_single and i + 1 < len(source):
                            body += source[i + 1]
                            i += 2
                            continue

                        if c == "'" and not sub_in_double and p != "\\":
                            sub_in_single = not sub_in_single
                        elif c == '"' and not sub_in_single and p != "\\":
                            sub_in_double = not sub_in_double
                        elif not sub_in_single and not sub_in_double:
                            if c == "(":
                                sub_depth += 1
                            elif c == ")":
                                sub_depth -= 1

                        i += 1

                    continue

                # Check for nested brace groups
                if inner == "{" and i + 1 < len(source) and source[i + 1].isspace():
                    nested_prev_is_boundary = inner_prev in " \t\n\r;|&("
                    if nested_prev_is_boundary:
                        depth += 1

                # Check for closing brace (before adding to body)
                if inner == "}" and (inner_prev == ";" or inner_prev.isspace()):
                    depth -= 1
                    if depth == 0:
                        break

                body += inner
                i += 1

            if body.strip():
                # Strip whitespace and trailing semicolons
                cleaned = body.strip().rstrip(";").strip()
                groups.append(cleaned)
                # Recurse to find nested braces
                groups.extend(extract_brace_groups(body))

            continue

        i += 1

    return groups
