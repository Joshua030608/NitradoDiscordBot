from __future__ import annotations

import asyncio
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

from .alert_format import EVENTS_PER_EMBED, build_event_embed_dicts, build_event_message_content
from .config import AppConfig
from .monitor import ArkLogMonitor, MonitorEvaluation, MonitorOptions
from .nitrado import NitradoClient, NitradoError, NitradoGameserver, NitradoService
from .parser import Event
from .rcon import ListPlayersResult, RconClient, RconError

try:
    import discord
    from discord import app_commands
except ImportError as exc:  # pragma: no cover - exercised by real bot startup.
    raise RuntimeError(
        "Discord bot mode requires discord.py. Install dependencies with "
        "`python3 -m pip install -r requirements.txt`."
    ) from exc


MAX_EMBEDS_PER_MESSAGE = 10
MAX_EVENTS_PER_DISCORD_MESSAGE = EVENTS_PER_EMBED * MAX_EMBEDS_PER_MESSAGE
MAX_RECENT_EVENTS = 50
T = TypeVar("T")


class ArkDiscordBot(discord.Client):
    def __init__(self, config: AppConfig, monitor_options: MonitorOptions) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.config = config
        self.monitor = ArkLogMonitor(config, monitor_options)
        self.tree = app_commands.CommandTree(self)
        self._poll_lock = asyncio.Lock()
        self._poll_task: asyncio.Task[None] | None = None
        self._last_poll_at: datetime | None = None
        self._last_poll_error: str | None = None
        self._last_sent_count = 0
        self._last_baseline_count = 0
        self._recent_events: deque[Event] = deque(maxlen=MAX_RECENT_EVENTS)
        self._commands_registered = False

    async def setup_hook(self) -> None:
        self._register_commands()
        guild = self._configured_guild()
        if guild is not None:
            synced = await self.tree.sync(guild=guild)
            print(f"Synced {len(synced)} Discord command group(s) to guild {guild.id}.")
        else:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} global Discord command group(s).")

        self._poll_task = asyncio.create_task(self._poll_loop(), name="ark-log-poll-loop")

    async def close(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await super().close()

    async def on_ready(self) -> None:
        print(f"Discord bot logged in as {self.user}.")

    def _register_commands(self) -> None:
        if self._commands_registered:
            return

        ark_group = app_commands.Group(name="ark", description="ARK server tools")

        @ark_group.command(name="status", description="Show bot, FTP, and RCON status")
        async def status(interaction: discord.Interaction) -> None:
            await self._status_command(interaction)

        @ark_group.command(name="players", description="Show connected ARK players using RCON")
        async def players(interaction: discord.Interaction) -> None:
            await self._players_command(interaction)

        @ark_group.command(name="saveworld", description="Save the ARK world using RCON")
        async def saveworld(interaction: discord.Interaction) -> None:
            await self._saveworld_command(interaction)

        @ark_group.command(name="broadcast", description="Send an in-game broadcast using RCON")
        @app_commands.describe(message="Message to broadcast in-game")
        async def broadcast(interaction: discord.Interaction, message: str) -> None:
            await self._broadcast_command(interaction, message)

        @ark_group.command(name="recent", description="Show recent timeline events sent by the bot")
        @app_commands.describe(count="Number of recent events to show")
        async def recent(interaction: discord.Interaction, count: int = 10) -> None:
            await self._recent_command(interaction, count)

        nitrado_group = app_commands.Group(
            name="nitrado",
            description="Nitrado hosting controls",
        )

        @nitrado_group.command(name="status", description="Show Nitrado gameserver status")
        async def nitrado_status(interaction: discord.Interaction) -> None:
            await self._nitrado_status_command(interaction)

        @nitrado_group.command(name="services", description="List Nitrado services visible to the token")
        async def nitrado_services(interaction: discord.Interaction) -> None:
            await self._nitrado_services_command(interaction)

        @nitrado_group.command(name="restart", description="Restart the Nitrado gameserver")
        @app_commands.describe(
            confirm="Required. Set true to confirm the restart.",
            message="Optional note for Nitrado logs and in-game chat.",
        )
        async def nitrado_restart(
            interaction: discord.Interaction,
            confirm: bool = False,
            message: str = "",
        ) -> None:
            await self._nitrado_restart_command(interaction, confirm, message)

        @nitrado_group.command(name="stop", description="Stop the Nitrado gameserver")
        @app_commands.describe(
            confirm="Required. Set true to confirm stopping the server.",
            message="Optional note for Nitrado logs and in-game chat.",
        )
        async def nitrado_stop(
            interaction: discord.Interaction,
            confirm: bool = False,
            message: str = "",
        ) -> None:
            await self._nitrado_stop_command(interaction, confirm, message)

        @nitrado_group.command(name="start", description="Start the Nitrado gameserver")
        async def nitrado_start(interaction: discord.Interaction) -> None:
            await self._nitrado_start_command(interaction)

        guild = self._configured_guild()
        self.tree.add_command(ark_group, guild=guild)
        self.tree.add_command(nitrado_group, guild=guild)
        self._commands_registered = True

    def _configured_guild(self) -> discord.Object | None:
        if self.config.discord_guild_id is None:
            return None
        return discord.Object(id=self.config.discord_guild_id)

    async def _poll_loop(self) -> None:
        await self.wait_until_ready()
        print(f"Discord bot monitor started. Polling every {self.config.poll_seconds}s.")
        while not self.is_closed():
            async with self._poll_lock:
                await self._poll_once()
            await asyncio.sleep(self.config.poll_seconds)

    async def _poll_once(self) -> None:
        try:
            evaluation = await asyncio.to_thread(self.monitor.evaluate_once)
            if evaluation.events_to_send:
                await self._send_event_alerts(evaluation)
                self._recent_events.extend(evaluation.events_to_send)

            await asyncio.to_thread(self.monitor.commit_evaluation, evaluation)
            self._last_poll_at = datetime.now(timezone.utc)
            self._last_poll_error = None
            self._last_sent_count = len(evaluation.events_to_send)
            self._last_baseline_count = (
                len(evaluation.report.events) if evaluation.baseline_saved else 0
            )
            if evaluation.events_to_send:
                print(f"Posted {len(evaluation.events_to_send)} ARK event(s) to Discord.")
        except Exception as exc:
            self._last_poll_at = datetime.now(timezone.utc)
            self._last_poll_error = str(exc)
            print(f"Discord bot poll error: {exc}", file=sys.stderr)

    async def _send_event_alerts(self, evaluation: MonitorEvaluation) -> None:
        channel = await self._alert_channel()
        source_name = Path(evaluation.report.source).name
        server_name = self.config.server_name or evaluation.report.server_name

        for events in _chunks(evaluation.events_to_send, MAX_EVENTS_PER_DISCORD_MESSAGE):
            embeds = [
                discord.Embed.from_dict(embed)
                for embed in build_event_embed_dicts(
                    events,
                    self.config.timezone_name,
                    server_name=server_name,
                    source_name=source_name,
                )
            ]
            await channel.send(
                content=build_event_message_content(events, self.config.discord_user_id),
                embeds=embeds,
                allowed_mentions=_allowed_mentions_for_user(self.config.discord_user_id),
            )

    async def _alert_channel(self):
        channel_id = self.config.discord_alert_channel_id
        if channel_id is None:
            raise RuntimeError("Missing DISCORD_ALERT_CHANNEL_ID")

        channel = self.get_channel(channel_id)
        if channel is None:
            channel = await self.fetch_channel(channel_id)

        if not hasattr(channel, "send"):
            raise RuntimeError(f"Discord channel {channel_id} cannot receive messages")
        return channel

    async def _status_command(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="ARK bot status",
            color=0x2E90FA if self._last_poll_error is None else 0xD92D20,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Monitor", value=self._monitor_status(), inline=False)
        embed.add_field(name="RCON", value=self._rcon_status(), inline=False)
        embed.add_field(name="Nitrado", value=self._nitrado_config_status(), inline=False)
        embed.add_field(name="Discord", value=self._discord_status(), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _players_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(self._run_rcon, lambda client: client.list_players())
        except Exception as exc:
            await interaction.followup.send(_friendly_rcon_error(exc), ephemeral=True)
            return

        embed = _players_embed(result)
        await interaction.followup.send(embed=embed)

    async def _saveworld_command(self, interaction: discord.Interaction) -> None:
        if not await self._require_admin(interaction):
            return

        await interaction.response.defer(thinking=True)
        try:
            response = await asyncio.to_thread(self._run_rcon, lambda client: client.save_world())
        except Exception as exc:
            await interaction.followup.send(_friendly_rcon_error(exc), ephemeral=True)
            return

        detail = response or "The server accepted the SaveWorld command."
        await interaction.followup.send(f"SaveWorld sent. {detail}")

    async def _broadcast_command(self, interaction: discord.Interaction, message: str) -> None:
        if not await self._require_admin(interaction):
            return

        await interaction.response.defer(thinking=True)
        try:
            response = await asyncio.to_thread(
                self._run_rcon,
                lambda client: client.broadcast(message),
            )
        except Exception as exc:
            await interaction.followup.send(_friendly_rcon_error(exc), ephemeral=True)
            return

        detail = response or "The server accepted the broadcast command."
        await interaction.followup.send(f"Broadcast sent. {detail}")

    async def _recent_command(self, interaction: discord.Interaction, count: int = 10) -> None:
        clean_count = max(1, min(count, 25))
        events = list(self._recent_events)[-clean_count:]
        if not events:
            await interaction.response.send_message("No recent events in memory yet.", ephemeral=True)
            return

        embeds = [
            discord.Embed.from_dict(embed)
            for embed in build_event_embed_dicts(
                events,
                self.config.timezone_name,
                server_name=self.config.server_name,
                source_name="recent events",
            )
        ]
        await interaction.response.send_message(
            content=f"Showing {len(events)} recent ARK timeline event(s).",
            embeds=embeds,
            ephemeral=True,
        )

    async def _nitrado_status_command(self, interaction: discord.Interaction) -> None:
        if not await self._require_admin(interaction):
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            gameserver = await asyncio.to_thread(
                self._run_nitrado,
                lambda client: client.get_gameserver(),
            )
        except Exception as exc:
            await interaction.followup.send(_friendly_nitrado_error(exc), ephemeral=True)
            return

        await interaction.followup.send(embed=_nitrado_status_embed(gameserver), ephemeral=True)

    async def _nitrado_services_command(self, interaction: discord.Interaction) -> None:
        if not await self._require_admin(interaction):
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            services = await asyncio.to_thread(
                self._run_nitrado_allowing_missing_service,
                lambda client: client.list_services(),
            )
        except Exception as exc:
            await interaction.followup.send(_friendly_nitrado_error(exc), ephemeral=True)
            return

        await interaction.followup.send(embed=_nitrado_services_embed(services), ephemeral=True)

    async def _nitrado_restart_command(
        self,
        interaction: discord.Interaction,
        confirm: bool,
        message: str,
    ) -> None:
        if not await self._require_admin(interaction):
            return
        if not confirm:
            await interaction.response.send_message(
                "Restart not sent. Run `/nitrado restart confirm: true` to confirm.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            response = await asyncio.to_thread(
                self._run_nitrado,
                lambda client: client.restart(
                    message=message,
                    restart_message=message,
                ),
            )
        except Exception as exc:
            await interaction.followup.send(_friendly_nitrado_error(exc), ephemeral=True)
            return

        await interaction.followup.send(f"Nitrado restart requested. {response}", ephemeral=True)

    async def _nitrado_stop_command(
        self,
        interaction: discord.Interaction,
        confirm: bool,
        message: str,
    ) -> None:
        if not await self._require_admin(interaction):
            return
        if not confirm:
            await interaction.response.send_message(
                "Stop not sent. Run `/nitrado stop confirm: true` to confirm.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            response = await asyncio.to_thread(
                self._run_nitrado,
                lambda client: client.stop(
                    message=message,
                    stop_message=message,
                ),
            )
        except Exception as exc:
            await interaction.followup.send(_friendly_nitrado_error(exc), ephemeral=True)
            return

        await interaction.followup.send(f"Nitrado stop requested. {response}", ephemeral=True)

    async def _nitrado_start_command(self, interaction: discord.Interaction) -> None:
        if not await self._require_admin(interaction):
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            response = await asyncio.to_thread(
                self._run_nitrado,
                lambda client: client.start(),
            )
        except Exception as exc:
            await interaction.followup.send(_friendly_nitrado_error(exc), ephemeral=True)
            return

        await interaction.followup.send(f"Nitrado start requested. {response}", ephemeral=True)

    async def _require_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in self.config.discord_admin_user_ids:
            return True

        await interaction.response.send_message(
            "Only configured ARK bot admins can run that command.",
            ephemeral=True,
        )
        return False

    def _run_rcon(self, action: Callable[[RconClient], T]) -> T:
        missing = self.config.missing_rcon_fields()
        if missing:
            raise ValueError("Missing RCON configuration: " + ", ".join(missing))

        with RconClient(
            host=self.config.rcon_host or "",
            port=self.config.rcon_port or 0,
            password=self.config.rcon_password or "",
            timeout_seconds=self.config.rcon_timeout_seconds,
        ) as client:
            return action(client)

    def _run_nitrado(self, action: Callable[[NitradoClient], T]) -> T:
        missing = self.config.missing_nitrado_fields()
        if missing:
            raise ValueError("Missing Nitrado configuration: " + ", ".join(missing))
        return self._run_nitrado_allowing_missing_service(action)

    def _run_nitrado_allowing_missing_service(
        self,
        action: Callable[[NitradoClient], T],
    ) -> T:
        if not self.config.nitrado_api_token:
            raise ValueError("Missing NITRADO_API_TOKEN")

        client = NitradoClient(
            api_token=self.config.nitrado_api_token,
            service_id=self.config.nitrado_service_id,
            timeout_seconds=self.config.nitrado_timeout_seconds,
        )
        return action(client)

    def _monitor_status(self) -> str:
        last_poll = _discord_timestamp(self._last_poll_at) if self._last_poll_at else "never"
        lines = [
            f"Polling every {self.config.poll_seconds}s",
            f"Last poll: {last_poll}",
            f"Last sent batch: {self._last_sent_count} event(s)",
        ]
        if self._last_baseline_count:
            lines.append(f"Baseline saved: {self._last_baseline_count} existing event(s)")
        if self._last_poll_error:
            lines.append(f"Last error: {_truncate(self._last_poll_error, 180)}")
        return "\n".join(lines)

    def _rcon_status(self) -> str:
        missing = self.config.missing_rcon_fields()
        if missing:
            return "Not configured: " + ", ".join(missing)
        return f"Configured for {self.config.rcon_host}:{self.config.rcon_port}"

    def _nitrado_config_status(self) -> str:
        missing = self.config.missing_nitrado_fields()
        if missing:
            return "Not configured: " + ", ".join(missing)
        return f"Configured for service {self.config.nitrado_service_id}"

    def _discord_status(self) -> str:
        guild = str(self.config.discord_guild_id) if self.config.discord_guild_id else "global"
        channel = (
            f"<#{self.config.discord_alert_channel_id}>"
            if self.config.discord_alert_channel_id
            else "not configured"
        )
        admin_count = len(self.config.discord_admin_user_ids)
        return f"Commands: {guild}\nAlerts: {channel}\nAdmins: {admin_count}"


def run_discord_bot(config: AppConfig, monitor_options: MonitorOptions) -> None:
    missing = config.missing_discord_bot_fields()
    if missing:
        raise ValueError("Missing Discord bot configuration: " + ", ".join(missing))

    bot = ArkDiscordBot(config, monitor_options)
    bot.run(config.discord_bot_token or "")


def _allowed_mentions_for_user(discord_user_id: str | None):
    if not discord_user_id:
        return discord.AllowedMentions.none()
    try:
        user = discord.Object(id=int(discord_user_id))
    except ValueError:
        return discord.AllowedMentions.none()
    return discord.AllowedMentions(
        everyone=False,
        users=[user],
        roles=False,
        replied_user=False,
    )


def _players_embed(result: ListPlayersResult) -> discord.Embed:
    color = 0x12B76A if result.players else 0x667085
    embed = discord.Embed(
        title="ARK players",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if not result.players:
        embed.description = "No players are online."
        if result.raw:
            embed.set_footer(text=_truncate(result.raw, 180))
        return embed

    lines = []
    for player in result.players:
        steam = f" ({player.steam_id})" if player.steam_id else ""
        lines.append(f"{player.index}. {player.name}{steam}")
    embed.description = "\n".join(lines)
    return embed


def _nitrado_status_embed(gameserver: NitradoGameserver) -> discord.Embed:
    color = _nitrado_status_color(gameserver.status)
    embed = discord.Embed(
        title="Nitrado gameserver",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Service ID", value=str(gameserver.service_id), inline=True)
    embed.add_field(name="Status", value=gameserver.status, inline=True)
    embed.add_field(name="Game", value=gameserver.game_human or gameserver.game or "unknown", inline=True)
    embed.add_field(name="Address", value=gameserver.address or "unknown", inline=True)
    embed.add_field(name="Query Port", value=str(gameserver.query_port or "unknown"), inline=True)
    embed.add_field(name="RCON Port", value=str(gameserver.rcon_port or "unknown"), inline=True)
    if gameserver.slots is not None:
        embed.add_field(name="Slots", value=str(gameserver.slots), inline=True)
    return embed


def _nitrado_services_embed(services: list[NitradoService]) -> discord.Embed:
    embed = discord.Embed(
        title="Nitrado services",
        color=0x2E90FA,
        timestamp=datetime.now(timezone.utc),
    )
    if not services:
        embed.description = "No services were returned for this token."
        return embed

    lines = []
    for service in services[:10]:
        bits = [
            f"`{service.id}`",
            service.status,
            service.game or service.type,
        ]
        if service.name:
            bits.append(service.name)
        if service.address:
            bits.append(service.address)
        lines.append(" - ".join(bits))
    if len(services) > 10:
        lines.append(f"...and {len(services) - 10} more")
    embed.description = "\n".join(lines)
    embed.set_footer(text="Use the matching service ID as NITRADO_SERVICE_ID.")
    return embed


def _friendly_rcon_error(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, RconError):
        return f"RCON failed: {exc}"
    return f"RCON command failed: {exc}"


def _friendly_nitrado_error(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, NitradoError):
        return f"Nitrado API failed: {exc}"
    return f"Nitrado command failed: {exc}"


def _nitrado_status_color(status: str) -> int:
    normalized = status.casefold()
    if normalized == "started":
        return 0x12B76A
    if normalized in {"stopping", "restarting", "installing"}:
        return 0xF79009
    if normalized in {"stopped", "suspended", "adminlocked"}:
        return 0xD92D20
    return 0x667085


def _discord_timestamp(value: datetime) -> str:
    return f"<t:{int(value.timestamp())}:R>"


def _chunks(items: list[Event], size: int) -> list[list[Event]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
