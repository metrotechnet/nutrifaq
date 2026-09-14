# Rate limiting notes

This project uses `slowapi` to apply basic request-rate limits in the FastAPI app.

## Current configuration

In `app.py` the app currently defines:

```python
limiter = Limiter(key_func=get_remote_address, default_limits=["30 per day", "10 per hour"])
```

That means requests are limited by client IP to:

- 30 requests per day
- 10 requests per hour

## Behavior

When a client exceeds the configured limit, the server returns a 429 response. The app also has a global exception handler for `RateLimitExceeded`.

## Why this matters

This helps reduce accidental abuse, brute-force attempts, or repeated automated requests while the app is still in a lighter development or testing mode.

## Notes

- The current project setup is intentionally simple and does not include a heavier production rate-limit stack such as Redis or Cloud Armor.
- This is a runtime safeguard rather than a security boundary by itself.
- The frontend avoids duplicate rapid submissions in the chat flow.
