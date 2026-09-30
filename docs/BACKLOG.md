# Backlog

Work that has been considered and deliberately deferred. Each entry says why it
was deferred and what would make it worth doing, so it can be picked up without
re-deriving the reasoning.

---

## Web UI access control (deferred 2026-09-29)

**Decision:** not needed while the app runs on a trusted home LAN. Revisit before
deploying anywhere with stricter security requirements (a shared network, a
server, anything reachable by people you do not trust).

**Current state**
- `stb serve` binds to `127.0.0.1` by default. `--host 0.0.0.0` exposes it to the
  LAN, and the running instance is started that way.
- There is no authentication and no CSRF protection. Every state-changing route
  (accept/reject/supersede a rule, resolve a conflict, ingest, drill, roleplay,
  debrief) is an unauthenticated POST.
- Anything that can reach the port can read and change everything, including
  debrief text and roleplay transcripts, which are personal.
- The exposure is not only LAN-wide. Because the POSTs are unauthenticated, a web
  page open in a browser that can reach the app can submit forms to it, even when
  it is bound to localhost only.

**When this is picked up**
1. Reject state-changing requests whose `Origin`/`Sec-Fetch-Site` does not match
   the request's own host (cheap CSRF defence, no user-visible change).
2. Optional shared secret, `STB_ACCESS_TOKEN`, required when the bind address is
   not loopback (cookie set from a one-time `?token=` link, or HTTP basic auth).
3. `TrustedHostMiddleware` with the configured hostnames, to blunt DNS rebinding.
4. TLS terminated by a reverse proxy; the app itself stays plain HTTP.
5. State in `docs/DECISIONS.md` what the trust boundary is, since the practice
   data is sensitive in a way the source library is not.

**Done when:** a request from another origin, or without the token when one is
configured, is rejected, with tests for both.
