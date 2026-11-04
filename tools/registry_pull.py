#!/usr/bin/env python3
"""Pull a container image through the egress proxy using only stdlib HTTP,
then assemble a `docker load`-able tar. Exists because dockerd's own TLS
through this VM's intercepting proxy times out on every registry, while
Python/curl through the same proxy work fine.

Usage: registry_pull.py <image-ref> [<image-ref> ...]
  e.g. registry_pull.py postgres:16-alpine ghcr.io/sandbox-quantum/setup:0.31.0
Output tars land in ./pulled/<repo>_<tag>.tar and are docker-loaded if the
daemon answers.
"""
import gzip
import io
import json
import os
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request

ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pulled")
os.makedirs(OUTDIR, exist_ok=True)


class NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            old_host = urllib.parse.urlparse(req.full_url).netloc
            new_host = urllib.parse.urlparse(newurl).netloc
            if old_host != new_host:
                new.remove_header("Authorization")
        return new


opener = urllib.request.build_opener(NoAuthRedirect)


def get(url, token=None, accept=None, stream_to=None):
    # The egress proxy drops streams often enough that every fetch retries.
    last = None
    for attempt in range(6):
        try:
            req = urllib.request.Request(url)
            if token:
                req.add_header("Authorization", f"Bearer {token}")
            if accept:
                req.add_header("Accept", accept)
            resp = opener.open(req, timeout=300)
            if stream_to is not None:
                with open(stream_to, "wb") as f:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                return None
            return resp.read()
        except Exception as e:  # noqa: BLE001 - retry any transport failure
            last = e
            print(f"  retry {attempt + 1}/6 after {type(e).__name__}", flush=True)
            import time
            time.sleep(3 * (attempt + 1))
    raise last


def parse_ref(ref):
    if "/" not in ref.split(":")[0]:
        ref = "library/" + ref
    if "." not in ref.split("/")[0] and ":" not in ref.split("/")[0]:
        ref = "docker.io/" + ref
    registry, rest = ref.split("/", 1)
    if ":" in rest:
        repo, tag = rest.rsplit(":", 1)
    else:
        repo, tag = rest, "latest"
    return registry, repo, tag


def get_token(registry, repo):
    if registry == "docker.io":
        url = ("https://auth.docker.io/token?service=registry.docker.io"
               f"&scope=repository:{repo}:pull")
    else:
        url = f"https://{registry}/token?service={registry}&scope=repository:{repo}:pull"
    data = json.loads(get(url))
    return data["token"]


def pull(ref):
    registry, repo, tag = parse_ref(ref)
    api_host = "registry-1.docker.io" if registry == "docker.io" else registry
    token = get_token(registry, repo)
    base = f"https://{api_host}/v2/{repo}"
    manifest = json.loads(get(f"{base}/manifests/{tag}", token, ACCEPT))
    if "manifests" in manifest:  # index / manifest list -> pick linux/amd64
        digest = None
        for m in manifest["manifests"]:
            p = m.get("platform", {})
            if p.get("os") == "linux" and p.get("architecture") == "amd64":
                digest = m["digest"]
                break
        if digest is None:
            raise SystemExit(f"{ref}: no linux/amd64 manifest in index")
        manifest = json.loads(get(f"{base}/manifests/{digest}", token, ACCEPT))
    config_digest = manifest["config"]["digest"]
    config_name = config_digest.split(":", 1)[1] + ".json"
    tmp = os.path.join(OUTDIR, f".tmp-{repo.replace('/', '_')}-{tag}")
    os.makedirs(tmp, exist_ok=True)
    get(f"{base}/blobs/{config_digest}", token, stream_to=os.path.join(tmp, config_name))
    layer_names = []
    for layer in manifest["layers"]:
        d = layer["digest"].split(":", 1)[1]
        gz = os.path.join(tmp, d + ".tar.gz")
        raw = os.path.join(tmp, d + ".tar")
        get(f"{base}/blobs/{layer['digest']}", token, stream_to=gz)
        media = layer.get("mediaType", "")
        if "gzip" in media:
            with gzip.open(gz, "rb") as src, open(raw, "wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)
            os.remove(gz)
        else:
            os.rename(gz, raw)
        layer_names.append(d + ".tar")
        print(f"  layer {d[:12]} ok ({os.path.getsize(raw)//(1<<20)} MB)", flush=True)
    manifest_json = [{"Config": config_name,
                      "RepoTags": [f"{repo}:{tag}"],
                      "Layers": layer_names}]
    with open(os.path.join(tmp, "manifest.json"), "w") as f:
        json.dump(manifest_json, f)
    out = os.path.join(OUTDIR, f"{repo.replace('/', '_')}_{tag}.tar")
    with tarfile.open(out, "w") as tar:
        for name in [config_name, "manifest.json"] + layer_names:
            tar.add(os.path.join(tmp, name), arcname=name)
    for name in os.listdir(tmp):
        os.remove(os.path.join(tmp, name))
    os.rmdir(tmp)
    print(f"{ref} -> {out} ({os.path.getsize(out)//(1<<20)} MB)", flush=True)
    r = subprocess.run(["docker", "load", "-i", out], capture_output=True, text=True)
    print((r.stdout or r.stderr).strip(), flush=True)


if __name__ == "__main__":
    for ref in sys.argv[1:]:
        print(f"== pulling {ref}", flush=True)
        pull(ref)
