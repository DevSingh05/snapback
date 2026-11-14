# SNAPBACK for other agents (MCP)

SNAPBACK ships an [MCP](https://modelcontextprotocol.io) server, so Claude, ChatGPT and other
agents can check a rental listing and find places on a renter's behalf. It is a thin client over
SNAPBACK's own HTTP API: every rule, limit and verdict stays in the API, and code, never a
language model, sets the verdict.

- **Where:** `src/snapback/mcp_server.py`, built on the official MCP Python SDK (`mcp` 2.3.0,
  MIT; in 2.x the class `FastMCP` is called `MCPServer`).
- **Transport:** stdio by default. Streamable HTTP is opt-in (`--http`), binds to 127.0.0.1 only
  and needs a bearer token.
- **Needs:** the API running (`make api`, port 8000), or `SNAPBACK_API_URL` pointing at one.

## Connect it

Start the API in one terminal:

```sh
make api
```

### Claude Code

From the repo root:

```sh
claude mcp add snapback -- uv run python -m snapback.mcp_server
```

Against an API on another port or host:

```sh
claude mcp add snapback --env SNAPBACK_API_URL=http://localhost:8014 -- uv run python -m snapback.mcp_server
```

Then `/mcp` in Claude Code lists `snapback` and its six tools.

### Claude Desktop

Add this to `claude_desktop_config.json` (Settings, Developer, Edit Config). Use the absolute
path of your checkout:

```json
{
  "mcpServers": {
    "snapback": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/snapback",
        "python",
        "-m",
        "snapback.mcp_server"
      ],
      "env": { "SNAPBACK_API_URL": "http://localhost:8000" }
    }
  }
}
```

### Any MCP client over HTTP

```sh
SNAPBACK_MCP_TOKEN=pick-a-long-random-string uv run python -m snapback.mcp_server --http --port 8765
```

The endpoint is `http://127.0.0.1:8765/mcp`. Send `Authorization: Bearer <token>` on every
request. Without `SNAPBACK_MCP_TOKEN` the server makes a token for the run and prints it once to
your terminal. The server holds one renter's case tokens per process, so run it for yourself on
your own machine, never as a shared or public service.

`make mcp` runs the stdio server directly.

## Settings

| Variable                   | Default                 | What it is                            |
| -------------------------- | ----------------------- | ------------------------------------- |
| `SNAPBACK_API_URL`         | `http://localhost:8000` | SNAPBACK's API                        |
| `SNAPBACK_PUBLIC_BASE_URL` | `http://localhost:5173` | The web app, for the links in results |
| `SNAPBACK_MCP_TOKEN`       | one per run             | HTTP mode's bearer token              |

## Tools

| Tool                          | Arguments                                       | What it returns                                                                                                        |
| ----------------------------- | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `snapback_check_listing`      | `ad_text`, `photo_urls` = [], `max_rent` = null | Starts a check. The case id, LIVE or FIXTURE, the status, the verdict once known, a link to the result page.           |
| `snapback_get_verdict`        | `case_id`                                       | The card: the verdict words, every check line with its status and LIVE or FIXTURE, what is not checked, one next step. |
| `snapback_find_places`        | `brief`                                         | The Finder's reply, its picks (each with a Walk it first link) and any proposal that needs the renter's yes.           |
| `snapback_accept_preference`  | `proposal_id`, `yes` (a real boolean)           | The renter's yes or no on a Finder proposal. Only after the renter has answered.                                       |
| `snapback_walk_summary`       | `case_id`                                       | The walk's rooms, which ad photo landed in which room, the coverage line, a link to Walk it first.                     |
| `snapback_draft_tour_request` | `case_id`, `place_id`                           | A tour request drafted to the leasing office on record. Draft only: nothing is sent.                                   |

What every tool keeps to:

- **No secrets.** The case and Finder tokens the API hands out stay inside the MCP server and
  travel in headers only. No result carries one; `read_token` reads "held by this MCP server;
  never shown".
- **LIVE or FIXTURE** on every result, and on every card line.
- **Code sets the verdict.** `snapback_get_verdict` repeats `snapback.verdict.decide` and the
  card's own words. The server never picks, softens or strengthens a state.
- **Nothing beyond the web app.** Results carry what the web app already shows: card lines,
  room names, photo placements, the code-written pick lines. No scan ids, poses, match counts or
  raw record fields.
- **Plain errors.** A failure comes back as one sentence, such as "No case with that id." or
  "SNAPBACK's API is not reachable at http://localhost:8000. Start it with `make api`."
- **Photos only from the renter.** `photo_urls` must be links the renter gave. Each is fetched
  over http or https from a public host (no private or loopback addresses, redirects checked
  too), must be an image, and is capped at 10 MB; 10 photos at most.
- **The renter decides.** A Finder proposal changes nothing until `snapback_accept_preference`
  carries the renter's own yes. A tour request is a draft the renter sends, or not.

## Example conversation

Run against the fixture API (`SNAPBACK_DATA_SOURCE=fixture`, synthetic team-made data). The
tool results are trimmed.

> **Renter:** I found a 1 bed near Montrose for $1,350. The poster says the owner is overseas,
> so no viewing, and wants a Zelle deposit today. Is it real?

The agent calls `snapback_check_listing` with the ad text:

```json
{
  "case_id": "SFVE",
  "source": "FIXTURE",
  "status": "waiting_for_approval",
  "challenge_drafted": true,
  "read_token": "held by this MCP server; never shown",
  "result_url": "http://localhost:5173/case/SFVE",
  "next_action": "Open the result page and decide whether to send the drafted photo challenge to the poster. Send no money meanwhile."
}
```

Then `snapback_get_verdict` with `SFVE`:

```json
{
  "source": "FIXTURE",
  "verdict": "Hold off for now",
  "verdict_set_by": "code (snapback.verdict.decide), never a language model",
  "checks": [
    {
      "row": "PRICE",
      "check": "Payment ask",
      "status": "Warning",
      "says": "Zelle before a viewing. Red flag.",
      "source": "FIXTURE"
    },
    {
      "row": "PRICE",
      "check": "Pressure",
      "status": "Warning",
      "says": "They say they cannot show the unit in person. Red flag.",
      "source": "FIXTURE"
    }
  ],
  "not_checked": ["ID", "lease", "ownership"]
}
```

> **Agent:** SNAPBACK says **hold off for now** (fixture data). The ad asks for Zelle before a
> viewing and says the unit cannot be shown in person; both are red flags on its card. It has
> drafted a photo challenge for the poster: open the result page to read it and decide whether
> to send it. Send no money meanwhile. Want me to look for other places?
>
> **Renter:** Yes. 1 bed under 1500, no walk-ups.

`snapback_find_places` with that brief:

```json
{
  "source": "FIXTURE",
  "session": "started",
  "reply": "I noticed you said no walk-ups. Skip walk-ups from now on? Nothing changes until you say yes. Leading the list: 3 places.",
  "proposals": [
    { "proposal_id": "pr-1", "question": "Skip walk-ups from now on?", "status": "proposed" }
  ],
  "needs_renter_yes": true,
  "picks": [
    {
      "rank": 1,
      "place_id": "fx-fnd-05",
      "line": "Apartment, 2 floor plans, from $980 a month, as of CoStar's last research",
      "walkup": true
    }
  ]
}
```

> **Agent:** Three places lead the list. SNAPBACK asks: skip walk-ups from now on? Nothing
> changes until you say yes.
>
> **Renter:** Yes, skip them.

Only now does the agent call `snapback_accept_preference` with `{"proposal_id": "pr-1", "yes": true}`:

```json
{
  "source": "FIXTURE",
  "status": "accepted",
  "result": "Saved. The Finder applies it from the next search."
}
```

The next `snapback_find_places` call leads with places that are not walk-ups.
