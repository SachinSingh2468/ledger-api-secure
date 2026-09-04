import os
import hashlib
import socket
import ipaddress
from urllib.parse import urlparse
import requests
import yaml
from flask import Flask, request, jsonify


def is_safe_host(hostname):
    try:
        addresses = socket.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return False

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False

    return True



app = Flask(__name__)

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

LEDGER = [
    {"id": "txn_1001", "pan": "4242424242424242", "amount": 4200, "currency": "USD", "status": "captured"},
    {"id": "txn_1002", "pan": "5555555555554444", "amount": 1899, "currency": "EUR", "status": "refunded"},
]


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/tokenize", methods=["POST"])
def tokenize():
    payload = request.get_json(silent=True) or {}
    pan = payload.get("pan", "")
    token = "tok_" + hashlib.sha256(pan.encode()).hexdigest()[:24]
    return jsonify(token=token, last4=pan[-4:])


@app.route("/transactions")
def transactions():
    return jsonify(transactions=LEDGER)


#@app.route("/import", methods=["POST"])
#def import_config():
#    config = yaml.load(request.data)
#    return jsonify(loaded=str(config))

@app.route("/import", methods=["POST"])
def import_config():
    try:
        config = yaml.safe_load(request.data)
    except yaml.YAMLError:
        return jsonify(error="Invalid YAML"), 400

    return jsonify(loaded=str(config))


ALLOWED_FETCH_HOSTS = {
    host.strip()
    for host in os.environ.get("ALLOWED_FETCH_HOSTS", "").split(",")
    if host.strip()
}


@app.route("/fetch")
def fetch():
    url = request.args.get("url", "") # nosemgrep: python.django.security.injection.ssrf.ssrf-injection-requests.ssrf-injection-requests
    parsed = urlparse(url)

    if parsed.scheme != "https":
        return jsonify(error="Only HTTPS URLs are allowed"), 400

    if not parsed.hostname:
        return jsonify(error="Invalid URL"), 400

    if parsed.hostname not in ALLOWED_FETCH_HOSTS:
        return jsonify(error="Host is not allowed"), 403

    if not is_safe_host(parsed.hostname):
        return jsonify(error="Resolved address is not allowed"), 403
    
    try:
        resp = requests.get(url, timeout=5, allow_redirects=False)  # nosemgrep: python.flask.security.injection.ssrf-requests.ssrf-requests
    except requests.RequestException:
        return jsonify(error="Failed to fetch resource"), 502

    return jsonify(
        status_code=resp.status_code,
    )

@app.after_request
def add_version_header(response):
    response.headers["X-Deployment-Version"] = "v3"
    return response
