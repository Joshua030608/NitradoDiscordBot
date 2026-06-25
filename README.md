# Nitrado Discord ARK Log Bot

Polls a Nitrado ARK: Survival Ascended `ShooterGame.log` over FTP, extracts the
same important events that appear in the `ArkLogCleaner` clean timeline, and
sends new events to Discord while mentioning you.

The first version uses a Discord webhook instead of a full gateway bot. That is
simpler to host on AWS EC2, does not need slash-command setup, and still supports
direct user pings. A full Discord bot can be added later if you want commands
like `/players`, `/last-crash`, or `/mute-alerts`.

## Project Steps

1. Build and test the Python log monitor locally.
2. Create a Discord server/channel and a webhook for alerts.
3. Confirm the Nitrado FTP host, username, password, and remote
   `ShooterGame.log` path.
4. Run the monitor locally in dry-run mode, then with the webhook enabled.
5. Create an AWS Free Tier EC2 instance.
6. Copy the repo and `.env` to EC2.
7. Configure a `systemd` service so the bot starts automatically and restarts
   after crashes or reboots.
8. Optionally add RCON-powered features after the alerting loop is stable.

## Local Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

Edit `.env` with your Discord webhook, Discord user ID, and FTP details.

This project currently uses only Python's standard library, so there is no
`pip install` step.

Send one test message to the configured webhook:

```sh
python3 -m ark_log_bot --test-discord
```

## Test With Your Downloaded Log

Dry-run the parser without posting to Discord:

```sh
python3 -m ark_log_bot \
  --local-log /Users/joshuaford/Downloads/ShooterGame.log \
  --once \
  --send-existing \
  --no-discord \
  --print-events
```

Run the unit tests:

```sh
python3 -m unittest discover
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

The monitor stores its seen-event state in `.ark-log-bot-state.json` by default.
If `ShooterGame.log` rotates or shrinks after a server restart, the bot treats
the new file as fresh and sends the new startup/timeline events.

## Configuration

| Variable | Purpose |
| --- | --- |
| `DISCORD_WEBHOOK_URL` | Discord channel webhook URL. |
| `DISCORD_USER_ID` | Your numeric Discord user ID for `<@id>` pings. |
| `FTP_HOST` | Nitrado FTP host. |
| `FTP_PORT` | FTP port, usually `21`. |
| `FTP_USERNAME` | FTP username. |
| `FTP_PASSWORD` | FTP password. |
| `FTP_PATH` | Remote path to `ShooterGame.log`. |
| `FTP_USE_TLS` | Set `true` for explicit FTP over TLS if your host requires it. |
| `POLL_SECONDS` | Seconds between checks. |
| `TIMEZONE` | Display timezone, for example `America/New_York` or `local`. |
| `STATE_FILE` | JSON file used to remember sent events. |
| `SEND_EXISTING_ON_FIRST_RUN` | Send existing events when no state file exists. |
| `INCLUDE_SAVES` | Include every world-save event in Discord alerts. |
| `MAX_SEEN_EVENTS` | Maximum remembered event fingerprints. |
