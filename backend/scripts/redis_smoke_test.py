import sys
import redis

from app.config.settings import settings


def main() -> None:
    redis_url = settings.redis.url  # REDIS_URL env var, must be rediss://... (Upstash TCP endpoint)

    if not redis_url.startswith("rediss://"):
        print(
            f"[FAIL] REDIS_URL does not look like an Upstash TCP endpoint: {redis_url!r}\n"
            "Expected a rediss:// URL (NOT the https:// REST URL from the Upstash dashboard).",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        # decode_responses=True so PING returns a str, not bytes
        client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        result = client.ping()

        if result:
            print("PONG")
        else:
            print("[FAIL] PING returned falsy value:", result, file=sys.stderr)
            sys.exit(1)

        # Bonus check: exercise a SET/GET/TTL round trip since dedup.py (D2-09)
        # will rely on exactly this pattern with a 6h TTL.
        client.set("contagion:smoke_test", "ok", ex=10)
        value = client.get("contagion:smoke_test")
        assert value == "ok", f"Unexpected round-trip value: {value!r}"
        client.delete("contagion:smoke_test")

        print("[OK] Redis connection, PING, and SET/GET/TTL round-trip all verified.")

    except redis.exceptions.AuthenticationError as e:
        print(f"[FAIL] Auth error — check REDIS_URL password/token: {e}", file=sys.stderr)
        sys.exit(1)
    except redis.exceptions.ConnectionError as e:
        print(f"[FAIL] Could not connect to Upstash Redis: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()