# Nitrado API Plan

## Goals

- Add hosting-side controls without changing the existing ARK log alert loop.
- Keep all Nitrado commands admin-only.
- Require explicit confirmation for restart and stop actions.
- Let `/nitrado services` help discover the correct `NITRADO_SERVICE_ID` after
  an API token is added.

## Official Endpoints

The Nitrado docs app at `https://doc.nitrado.net` points to
`https://api.nitrado.net` as the API base URL. The generated docs list these
endpoints for the command layer:

- `GET /services`
- `GET /services/:id/gameservers`
- `GET /services/:id/gameservers/stats`
- `POST /services/:id/gameservers/restart`
- `POST /services/:id/gameservers/stop`
- `POST /services/:id/gameservers/games/start`

Restart accepts optional `message` and `restart_message` form fields. Stop
accepts optional `message` and `stop_message` form fields. Start requires a
`game` form field, which the client gets from the gameserver details response.

## Discord Commands

- `/nitrado status`
- `/nitrado services`
- `/nitrado restart confirm:`
- `/nitrado stop confirm:`
- `/nitrado start`

All commands require the invoking Discord user ID to be in
`DISCORD_ADMIN_USER_IDS`.

## Setup Sequence

1. Get a Nitrado API token.
2. Add `NITRADO_API_TOKEN` to `.env`.
3. Run `python3 -m ark_log_bot --nitrado-services`.
4. Pick the service ID for the ARK: Survival Ascended server.
5. Add `NITRADO_SERVICE_ID` to `.env`.
6. Run `python3 -m ark_log_bot --test-nitrado`.
7. Restart `ark-log-bot.service`.
