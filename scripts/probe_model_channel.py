from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("'").strip('"')
    return values


def output_text(data: dict[str, object]) -> str:
    direct = data.get("output_text")
    if isinstance(direct, str):
        return direct
    texts: list[str] = []
    output = data.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if (
                isinstance(part, dict)
                and part.get("type") == "output_text"
                and isinstance(part.get("text"), str)
            ):
                texts.append(part["text"])
    return "\n".join(texts)


def valid_supervisor_report(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) != {
        "status",
        "summary",
        "signals",
        "recommendations",
        "requires_human",
    }:
        return False
    return (
        value.get("status") in {"healthy", "watch", "critical"}
        and isinstance(value.get("summary"), str)
        and isinstance(value.get("signals"), list)
        and all(isinstance(item, str) for item in value["signals"])
        and isinstance(value.get("recommendations"), list)
        and all(isinstance(item, str) for item in value["recommendations"])
        and isinstance(value.get("requires_human"), bool)
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a small synthetic read-only task against a model channel."
    )
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--model", action="append", required=True)
    args = parser.parse_args()

    config = load_env(args.env_file)
    base_url = (
        config.get("ARENA_SUPERVISOR_AI_BASE_URL") or config.get("AI_BASE_URL") or ""
    ).rstrip("/")
    api_key = config.get("ARENA_SUPERVISOR_AI_API_KEY") or config.get("AI_API_KEY") or ""
    if not base_url or not api_key:
        raise SystemExit("The model endpoint and key are required in the private env file.")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "arena-hero-supervisor-probe/1.0",
    }
    with httpx.Client(headers=headers, timeout=60.0) as client:
        for model in args.model:
            payload = {
                "model": model,
                "input": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "You are a read-only Arena Hero operations reviewer. "
                                    "Return valid JSON only and never execute recommendations."
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Review this synthetic supervisor task: the Agent has "
                                    "advanced through a short healthy window, the Core is "
                                    "alive, resources are 8/15, workers=4, cargo=0, and no "
                                    "current danger cells are visible. The sample contains "
                                    "five HARVEST events, four DEPOSIT events, and no lifecycle "
                                    "failures. Return exactly these fields: status "
                                    "(healthy|watch|critical), summary, signals (string array), "
                                    "recommendations (string array), requires_human (boolean)."
                                ),
                            }
                        ],
                    },
                ],
                "max_output_tokens": 400,
                "store": False,
                "stream": False,
            }
            started = time.monotonic()
            try:
                response = client.post(f"{base_url}/responses", json=payload)
            except httpx.HTTPError as exc:
                latency_ms = round((time.monotonic() - started) * 1000)
                print(
                    f"TASK model={model} status=error kind={type(exc).__name__} "
                    f"latency_ms={latency_ms}"
                )
                continue
            latency_ms = round((time.monotonic() - started) * 1000)
            if response.status_code != 200:
                print(
                    f"TASK model={model} status=error http={response.status_code} "
                    f"latency_ms={latency_ms} "
                    f"content_type={response.headers.get('content-type', 'unknown')}"
                )
                continue
            data = response.json()
            valid_report = False
            try:
                valid_report = valid_supervisor_report(json.loads(output_text(data)))
            except json.JSONDecodeError:
                pass
            print(
                f"TASK model={model} status=ok resolved={data.get('model')} "
                f"latency_ms={latency_ms} valid_report={str(valid_report).lower()}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
