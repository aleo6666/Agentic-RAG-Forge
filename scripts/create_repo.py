"""Create the GitHub repo using the credential stored in Windows Credential Manager.

Reads the token via `git credential fill` (never prints it), then calls the
GitHub REST API to create the repository. Falls back gracefully if the token
lacks repo scope.
"""
import json
import subprocess
import urllib.request


def get_credential():
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
    )
    fields = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            fields[k] = v
    return fields.get("username"), fields.get("password")


def api_request(token, method, url, payload=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "rag-forge-setup")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(payload).encode()
    else:
        data = None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    username, token = get_credential()
    if not token:
        print("NO_CREDENTIAL")
        return

    # Verify token + scopes
    status, me = api_request(token, "GET", "https://api.github.com/user")
    if status != 200:
        print(f"TOKEN_INVALID status={status}")
        return
    print(f"USER: {me.get('login')}")

    status, scopes = api_request(token, "GET", "https://api.github.com/rate_limit")
    # scopes header check needs a raw response; do a light check via a repo-creating dry run instead

    name = "Agentic-RAG-Forge"
    status, body = api_request(
        token,
        "POST",
        "https://api.github.com/user/repos",
        {
            "name": name,
            "description": "企业级 Agentic RAG 引擎 — LangGraph 自反思检索增强生成 + Web 控制台 + 对比评估",
            "private": False,
            "auto_init": False,
        },
    )
    if status in (200, 201):
        print(f"CREATED: {body['html_url']}")
    elif status == 422 and "already exists" in json.dumps(body):
        print(f"EXISTS: https://github.com/{username}/{name}")
    else:
        print(f"CREATE_FAILED status={status} body={json.dumps(body)[:300]}")


if __name__ == "__main__":
    main()
