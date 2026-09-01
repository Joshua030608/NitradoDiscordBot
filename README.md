# Nitrado Discord ARK Log Bot

Polls a Nitrado ARK: Survival Ascended `ShooterGame.log` over FTP, extracts the
same important events that appear in the `ArkLogCleaner` clean timeline, and
sends every new timeline event to Discord while mentioning you.

The bot supports two Discord modes:

- Webhook monitor mode posts clean embedded alerts to a channel webhook.
- Discord bot mode posts the same alerts and adds `/ark` slash commands powered
  by ARK RCON plus optional `/nitrado` hosting controls.

## Highlights

- Parses a remote ARK log into structured timeline events and suppresses
  duplicates across polling cycles.
- Uses FTP for log retrieval, RCON for live player presence and server commands,
  Discord for alerts and slash commands, and the Nitrado REST API for optional
  hosting controls.
- Persists monitor state across restarts and handles log rotation without
  replaying old events.
- Includes automated tests for parsing, monitoring, configuration, RCON packet
  handling, state persistence, alert formatting, and Nitrado API requests.

## Quick Start

Create a virtual environment, copy the configuration template, and install the
optional Discord bot dependency:

```sh
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

Edit `.env` with your Discord webhook, Discord user ID, and FTP details.

Install dependencies if you want Discord slash-command bot mode:

```sh
python3 -m pip install -r requirements.txt
```

Webhook monitor mode, FTP, parsing, and RCON packet handling use Python's
standard library. Discord bot mode needs `discord.py`.

Run the automated test suite:

```sh
python3 -m unittest discover
```

Send one test message to the configured webhook:

```sh
python3 -m ark_log_bot --test-discord
```

## Test With Your Downloaded Log

Dry-run the parser without posting to Discord:

```sh
python3 -m ark_log_bot \
  --local-log /path/to/ShooterGame.log \
  --once \
  --send-existing \
  --no-discord \
  --print-events
```

## Run Against FTP Once

If you do not know the exact remote log path, search FTP for it:

```sh
python3 -m ark_log_bot --find-log
```

This checks FTP, parses the log, prints new events, and does not send to Discord:

```sh
python3 -m ark_log_bot --once --no-discord --print-events
```

On the first normal run, the bot records the events already in the log but does
not send them. This prevents a giant first-run Discord dump. To intentionally
send all current timeline events, use `--send-existing` or set
`SEND_EXISTING_ON_FIRST_RUN=true`.

## Run Continuously

```sh
python3 -m ark_log_bot
```

If `ENABLE_DISCORD_BOT=true` and the Discord bot settings are present,
`python3 -m ark_log_bot` runs the gateway bot. Otherwise it runs the webhook
monitor. Use `--webhook-monitor` to force webhook mode, or `--bot` to force bot
mode.

The monitor stores its seen-event state in `.ark-log-bot-state.json` by default.
If `ShooterGame.log` rotates or shrinks after a server restart, the bot treats
the new file as fresh and sends the new startup/timeline events.

## Discord Bot Commands

ARK commands are registered under `/ark`.

| Command | Purpose |
| --- | --- |
| `/ark status` | Shows monitor health, last poll, alert channel, and RCON config status. |
| `/ark players` | Runs `ListPlayers` over RCON and shows connected players. |
| `/ark saveworld` | Runs `SaveWorld` over RCON. Admin-only. |
| `/ark broadcast message:` | Runs `Broadcast <message>` over RCON. Admin-only. |
| `/ark recent count:` | Shows recent timeline events that were sent by this process. |

Admin-only commands are limited to `DISCORD_ADMIN_USER_IDS`. If that variable is
empty, the bot defaults it to `DISCORD_USER_ID`.

Nitrado hosting commands are registered under `/nitrado`.

| Command | Purpose |
| --- | --- |
| `/nitrado status` | Shows Nitrado gameserver status and ports. Admin-only. |
| `/nitrado services` | Lists services visible to the API token, useful for finding `NITRADO_SERVICE_ID`. Admin-only. |
| `/nitrado restart confirm:` | Restarts the Nitrado gameserver. Requires `confirm: true`. Admin-only. |
| `/nitrado stop confirm:` | Stops the Nitrado gameserver. Requires `confirm: true`. Admin-only. |
| `/nitrado start` | Starts the Nitrado gameserver. Admin-only. |

## Test RCON

Fill in `RCON_HOST`, `RCON_PORT`, and `RCON_PASSWORD`, then test before enabling
slash commands:

```sh
python3 -m ark_log_bot --test-rcon
python3 -m ark_log_bot --rcon-saveworld
python3 -m ark_log_bot --rcon-command "Broadcast Bot test"
```

`SaveWorld` may return an empty response on success, so a clean connection and
no RCON exception is treated as accepted.

The bot also polls RCON for player presence when RCON is configured. This gives
faster join/leave alerts than waiting for Nitrado FTP to expose delayed
`ShooterGame.log` writes. Set `RCON_PRESENCE_POLL_SECONDS=0` to disable the
live presence watcher. Delayed FTP join/leave lines are suppressed only when
they happen close to a matching RCON live alert; tune that window with
`RCON_PRESENCE_DEDUPE_SECONDS`.

## Test Nitrado API

Fill in `NITRADO_API_TOKEN`, then list services to find the service ID:

```sh
python3 -m ark_log_bot --nitrado-services
```

After setting `NITRADO_SERVICE_ID`, check the configured gameserver:

```sh
python3 -m ark_log_bot --test-nitrado
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `DISCORD_WEBHOOK_URL` | Discord channel webhook URL. |
| `DISCORD_USER_ID` | Your numeric Discord user ID for `<@id>` pings. |
| `ENABLE_DISCORD_BOT` | Set `true` to run slash-command bot mode by default. |
| `DISCORD_BOT_TOKEN` | Bot token from the Discord Developer Portal. |
| `DISCORD_GUILD_ID` | Discord server ID. Guild commands update fastest. |
| `DISCORD_ALERT_CHANNEL_ID` | Channel ID where bot-mode alerts should be posted. |
| `DISCORD_ADMIN_USER_IDS` | Comma- or space-separated user IDs allowed to run admin RCON commands. |
| `FTP_HOST` | Nitrado FTP host. |
| `FTP_PORT` | FTP port, usually `21`. |
| `FTP_USERNAME` | FTP username. |
| `FTP_PASSWORD` | FTP password. |
| `FTP_PATH` | Remote path to `ShooterGame.log`. |
| `FTP_USE_TLS` | Set `true` for explicit FTP over TLS if your host requires it. |
| `RCON_HOST` | ARK server RCON host. Often shown in the Nitrado RCON panel. |
| `RCON_PORT` | ARK server RCON port. |
| `RCON_PASSWORD` | ARK RCON password. |
| `RCON_TIMEOUT_SECONDS` | Socket timeout for RCON connects and commands. |
| `RCON_PRESENCE_POLL_SECONDS` | Seconds between live RCON player join/leave checks. Set `0` to disable. |
| `RCON_PRESENCE_DEDUPE_SECONDS` | Seconds a delayed FTP join/leave can match a recent RCON live alert. |
| `NITRADO_API_TOKEN` | Nitrado API bearer token. |
| `NITRADO_SERVICE_ID` | Numeric Nitrado service ID for this gameserver. |
| `NITRADO_TIMEOUT_SECONDS` | HTTP timeout for Nitrado API calls. |
| `SERVER_NAME` | Optional display name for Discord alert footers. |
| `POLL_SECONDS` | Seconds between checks. |
| `TIMEZONE` | Display timezone, for example `America/New_York` or `local`. |
| `STATE_FILE` | JSON file used to remember sent events. |
| `SEND_EXISTING_ON_FIRST_RUN` | Send existing events when no state file exists. |
| `INCLUDE_SAVES` | Include every world-save event in Discord alerts. |
| `MAX_SEEN_EVENTS` | Maximum remembered event fingerprints. |

## Project Structure

```text
ark_log_bot/  Application modules: parsing, monitoring, FTP, RCON, Discord, and Nitrado API
deploy/       Example systemd service for an always-on host
docs/         Integration planning notes
tests/        Automated unit tests
```

## Security and Operations

- Keep credentials only in `.env`; the repository ignores that file and includes
  placeholders in `.env.example`.
- Restrict `DISCORD_ADMIN_USER_IDS` before enabling server-control commands.
- Start with `--no-discord` or dry-run behavior when validating a new log path or
  server configuration.
- The `deploy/ark-log-bot.service` example is a starting point for an EC2 or
  other Linux deployment; adapt paths and the service user before enabling it.
