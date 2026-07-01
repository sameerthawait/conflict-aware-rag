#!/usr/bin/env python
from dotenv import load_dotenv
load_dotenv()
import argparse
import sys
import os
import hashlib
import secrets
import yaml
import redis
from typing import Dict, Any

# Ensure root directory is on PATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.config_loader import load_config

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml"))


def load_config_raw() -> Dict[str, Any]:
    """Loads config.yaml directly to preserve structure and write changes back."""
    if not os.path.exists(CONFIG_PATH):
        print(f"Error: Configuration file not found at {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config_raw(config: Dict[str, Any]) -> None:
    """Saves the configuration dictionary back to config.yaml."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def handle_create_key(args: argparse.Namespace) -> None:
    """Generates a secure API key, hashes it, and updates config.yaml."""
    # Generate 32-character hex key
    raw_key = "rag-" + secrets.token_hex(16)
    hashed_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    config = load_config_raw()
    
    # Initialize config sections if missing
    security = config.setdefault("security", {})
    hashed_keys = security.setdefault("hashed_api_keys", {})

    rpm = args.rpm if args.rpm is not None else (100 if args.tier == "premium" else 20)
    tpd = args.tpd if args.tpd is not None else (1000000 if args.tier == "premium" else 100000)

    hashed_keys[hashed_key] = {
        "name": args.name,
        "tier": args.tier,
        "rate_limit_rpm": rpm,
        "token_limit_tpd": tpd
    }

    save_config_raw(config)

    print("\n" + "=" * 50)
    print("🔑 NEW API KEY GENERATED SUCCESSFULLY")
    print("=" * 50)
    print(f"Name:       {args.name}")
    print(f"Tier:       {args.tier}")
    print(f"RPM Limit:  {rpm}")
    print(f"TPD Limit:  {tpd}")
    print(f"Hash:       {hashed_key}")
    print("-" * 50)
    print(f"PLAINTEXT KEY:  {raw_key}")
    print("=" * 50)
    print("⚠️  WARNING: Copy the plaintext key now! It is NOT stored in plaintext and cannot be recovered.\n")


def handle_list_keys(args: argparse.Namespace) -> None:
    """Lists all configured API keys with their details."""
    config = load_config_raw()
    hashed_keys = config.get("security", {}).get("hashed_api_keys", {})

    if not hashed_keys:
        print("\nNo API keys configured.")
        return

    print("\n" + "=" * 105)
    print(f"{'Name':<20} | {'Tier':<10} | {'RPM':<6} | {'TPD':<10} | {'Hashed Key (Prefix)':<30}")
    print("=" * 105)
    for hashed_key, info in hashed_keys.items():
        name = info.get("name", "unnamed")
        tier = info.get("tier", "standard")
        rpm = info.get("rate_limit_rpm", "N/A")
        tpd = info.get("token_limit_tpd", "N/A")
        print(f"{name:<20} | {tier:<10} | {rpm:<6} | {tpd:<10} | {hashed_key[:30]}...")
    print("=" * 105 + "\n")


def handle_revoke_key(args: argparse.Namespace) -> None:
    """Revokes an API key by its name or SHA-256 hash."""
    config = load_config_raw()
    hashed_keys = config.get("security", {}).get("hashed_api_keys", {})

    if not hashed_keys:
        print("No API keys found to revoke.", file=sys.stderr)
        return

    target_hash = None
    if args.hash:
        target_hash = args.hash
    elif args.name:
        for kh, info in hashed_keys.items():
            if info.get("name") == args.name:
                target_hash = kh
                break

    if not target_hash or target_hash not in hashed_keys:
        print(f"Error: API key with identifier '{args.name or args.hash}' not found.", file=sys.stderr)
        sys.exit(1)

    key_info = hashed_keys.pop(target_hash)
    save_config_raw(config)

    print(f"\n✔ Successfully revoked API key '{key_info.get('name')}' (Hash: {target_hash[:10]}...).")


def handle_invalidate_cache(args: argparse.Namespace) -> None:
    """Clears all semantic query cache items in Redis."""
    config = load_config_raw()
    redis_conf = config.get("redis", {})
    
    if not redis_conf.get("enabled", True):
        print("Redis is disabled in configuration. Local in-memory cache will expire automatically.")
        return

    url = redis_conf.get("url", "redis://localhost:6379/0")
    try:
        r = redis.Redis.from_url(url, socket_timeout=2.0)
        # Find semantic cache keys (typically prepended with cache:)
        keys = r.keys("cache:*")
        if keys:
            r.delete(*keys)
            print(f"\n✔ Successfully invalidated {len(keys)} semantic cache keys in Redis.")
        else:
            print("\nNo cached entries found in Redis.")
    except Exception as e:
        print(f"Error: Failed to connect to Redis at {url}: {str(e)}", file=sys.stderr)
        sys.exit(1)


def handle_show_metrics(args: argparse.Namespace) -> None:
    """Directly queries Redis to display live token usages and active rate limiter keys."""
    config = load_config_raw()
    redis_conf = config.get("redis", {})
    
    if not redis_conf.get("enabled", True):
        print("Redis is disabled in config. Live statistics cannot be gathered.")
        return

    url = redis_conf.get("url", "redis://localhost:6379/0")
    try:
        r = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2.0)
        
        # Token budgets
        import time
        now = time.gmtime()
        day_str = time.strftime("%Y-%m-%d", now)
        month_str = time.strftime("%Y-%m", now)

        cost_keys = r.keys("cost:*:*")
        
        print("\n" + "=" * 80)
        print("📊 LIVE REDIS METRICS REPORT")
        print("=" * 80)
        
        # Parse token usage
        hashed_keys = config.get("security", {}).get("hashed_api_keys", {})
        
        print("\n[Token Budgets Usage]")
        print("-" * 80)
        print(f"{'Key Name':<20} | {'Period':<12} | {'Tokens Used':<15} | {'Redis Key':<30}")
        print("-" * 80)
        for key in cost_keys:
            # key format: cost:hash:YYYY-MM-DD or cost:hash:YYYY-MM
            parts = key.split(":")
            if len(parts) != 3:
                continue
            _, key_hash, date_part = parts
            
            # Lookup name
            name = hashed_keys.get(key_hash, {}).get("name", f"Unknown ({key_hash[:6]})")
            val = r.get(key)
            print(f"{name:<20} | {date_part:<12} | {val:<15} | {key:<30}")

        # RPM limits active keys
        rpm_keys = r.keys("ratelimit:*:rpm")
        print("\n[Active Rate Limiter Windows (RPM)]")
        print("-" * 80)
        print(f"{'Key Name':<20} | {'Hits in Window':<15} | {'TTL (Seconds)':<15}")
        print("-" * 80)
        for key in rpm_keys:
            parts = key.split(":")
            if len(parts) != 4:
                continue
            _, key_hash, _, _ = parts
            name = hashed_keys.get(key_hash, {}).get("name", f"Unknown ({key_hash[:6]})")
            val = r.get(key)
            ttl = r.ttl(key)
            print(f"{name:<20} | {val:<15} | {ttl:<15}")
            
        print("=" * 80 + "\n")
    except Exception as e:
        print(f"Error: Failed to gather metrics from Redis: {str(e)}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG Production System Administrator Command Line Interface.")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Administrative commands")

    # create-api-key subparser
    create_parser = subparsers.add_parser("create-api-key", help="Generate and register a new SHA-256 API key.")
    create_parser.add_argument("--name", type=str, required=True, help="Unique name/identifier for the key owner.")
    create_parser.add_argument("--tier", type=str, choices=["standard", "premium"], default="standard", help="API service tier.")
    create_parser.add_argument("--rpm", type=int, default=None, help="Custom requests per minute limit override.")
    create_parser.add_argument("--tpd", type=int, default=None, help="Custom tokens per day limit override.")

    # list-keys subparser
    subparsers.add_parser("list-keys", help="Display all configured API keys and settings.")

    # revoke-key subparser
    revoke_parser = subparsers.add_parser("revoke-api-key", help="Revoke/remove an API key registry.")
    group = revoke_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--name", type=str, help="Name of the API key to revoke.")
    group.add_argument("--hash", type=str, help="SHA-256 hash of the API key to revoke.")

    # invalidate-cache subparser
    subparsers.add_parser("invalidate-cache", help="Flush all semantic query caches from Redis storage.")

    # show-metrics subparser
    subparsers.add_parser("show-metrics", help="Examine live Redis token counters and active rate limiter windows.")

    args = parser.parse_args()

    if args.command == "create-api-key":
        handle_create_key(args)
    elif args.command == "list-keys":
        handle_list_keys(args)
    elif args.command == "revoke-api-key":
        handle_revoke_key(args)
    elif args.command == "invalidate-cache":
        handle_invalidate_cache(args)
    elif args.command == "show-metrics":
        handle_show_metrics(args)


if __name__ == "__main__":
    main()
