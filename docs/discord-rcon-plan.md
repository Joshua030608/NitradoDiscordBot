# Discord Bot and RCON Plan

## Goals

- Keep pinging `DISCORD_USER_ID` for every parsed ARK timeline event.
- Preserve webhook monitor mode as a fallback.
- Add Discord slash commands without requiring privileged gateway intents.
- Keep RCON commands narrow and explicit instead of exposing arbitrary RCON to
  every Discord user.

## Discord Design

- The bot registers one `/ark` command group.
- Guild-scoped commands are preferred during setup because Discord documents
  them as updating instantly.
- Long-running RCON commands call `interaction.response.defer()` before doing
  network work so Discord receives an initial interaction response quickly.
- Alerts use embed payloads and a restricted allowed-mentions object so the bot
  can mention the configured user without allowing broad accidental mentions.

References:

- Discord Application Commands: https://discord.com/developers/docs/interactions/application-commands
- Discord Receiving and Responding: https://discord.com/developers/docs/interactions/receiving-and-responding
- Discord Message Resource: https://discord.com/developers/docs/resources/message
- discord.py Interactions API: https://discordpy.readthedocs.io/en/stable/interactions/api.html

## RCON Design

- ARK RCON uses the Source-style TCP RCON packet format.
- The project implements the packet protocol directly with `socket` and
  `struct` so the bot does not depend on an unmaintained CLI wrapper.
- Supported bot commands are intentionally limited:
  - `ListPlayers` for `/ark players`
  - `SaveWorld` for `/ark saveworld`
  - `Broadcast <message>` for `/ark broadcast`
- The implementation handles authentication failure, malformed packets,
  connection errors, command timeouts, and multi-packet command responses.
- `ListPlayers` parsing accepts both `Name, SteamID` and `SteamID, Name` player
  orderings.

Reference:

- Valve Source RCON Protocol: https://developer.valvesoftware.com/wiki/Source_RCON_Protocol

## Deployment Sequence

1. Push the code and pull/copy it to EC2.
2. Install `requirements.txt` on EC2.
3. Create a Discord application and bot, invite it to the server with `bot` and
   `applications.commands` scopes.
4. Add `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, `DISCORD_ALERT_CHANNEL_ID`,
   `DISCORD_ADMIN_USER_IDS`, and RCON settings to `.env`.
5. Run `python3 -m ark_log_bot --test-rcon`.
6. Run `python3 -m ark_log_bot --bot` once interactively.
7. Restart `ark-log-bot.service`.
