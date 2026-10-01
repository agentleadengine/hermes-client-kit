"""Fail-closed Cloudflare Access RS256 JWT verifier for tool origins.

The team certs URL, issuer and audience are client configuration. JWKs are
fetched on demand and matched by kid, including during key rotation.
"""
import base64
import hashlib
import hmac
import json
import re
import time
from urllib.request import urlopen

DER_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")
CERTS_URL = re.compile(r"^https://[a-z0-9-]+\.cloudflareaccess\.com/cdn-cgi/access/certs$")


def b64(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid base64url")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify(token, config, fetch=None, now=None):
    if not token or len(token) > 16384:
        return False
    try:
        cfg = config if isinstance(config, dict) else json.loads(config)
        url = cfg["certs_url"]
        issuer = cfg["issuer"]
        audience = cfg["audience"]
        if not CERTS_URL.fullmatch(url) or issuer != url.removesuffix("/cdn-cgi/access/certs") or not audience:
            return False
        parts = token.split(".")
        if len(parts) != 3:
            return False
        header, claims = json.loads(b64(parts[0])), json.loads(b64(parts[1]))
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            return False
        now = int(time.time()) if now is None else now
        aud = claims.get("aud")
        if claims.get("iss") != issuer or audience not in (aud if isinstance(aud, list) else [aud]):
            return False
        if not isinstance(claims.get("exp"), int) or claims["exp"] <= now or claims.get("nbf", 0) > now:
            return False
        if claims.get("type") not in (None, "app"):
            return False
        body = fetch(url) if fetch else urlopen(url, timeout=3).read(200000)
        keys = json.loads(body)["keys"]
        key = next(k for k in keys if k.get("kid") == header["kid"] and k.get("kty") == "RSA" and k.get("alg") == "RS256" and k.get("use") == "sig")
        n, e = int.from_bytes(b64(key["n"]), "big"), int.from_bytes(b64(key["e"]), "big")
        signature = b64(parts[2])
        length = (n.bit_length() + 7) // 8
        if length < 256 or length > 1024 or len(signature) != length or e < 3 or e % 2 == 0:
            return False
        encoded = pow(int.from_bytes(signature, "big"), e, n).to_bytes(length, "big")
        digest = DER_SHA256 + hashlib.sha256(".".join(parts[:2]).encode()).digest()
        expected = b"\x00\x01" + b"\xff" * (length - len(digest) - 3) + b"\x00" + digest
        return hmac.compare_digest(encoded, expected)
    except (KeyError, ValueError, TypeError, StopIteration, OSError, OverflowError, json.JSONDecodeError):
        return False
