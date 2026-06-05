import subprocess
import os
import json
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Label, Input, Button
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.containers import Grid
from core.config import ConfigManager, MASTER_CONFIG_PATH


class TokenModal(ModalScreen):
    """Screen for adding environment token."""

    CSS = """
    TokenModal {
        align: center middle;
    }
    
    #dialog {
        grid-size: 2;
        grid-gutter: 1;
        grid-rows: 1 3 3 3;
        padding: 1 2;
        width: 50;
        height: 20;
        border: thick $primary;
        background: $surface;
    }
    
    #dialog-title {
        column-span: 2;
        text-align: center;
        text-style: bold;
    }
    
    #token_name {
        column-span: 2;
    }
    
    #token_value {
        column-span: 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Add Environment Token", id="dialog-title"),
            Input(placeholder="Token Key (e.g. GITHUB_TOKEN)", id="token_name"),
            Input(placeholder="Token Value", id="token_value", password=True),
            Button("Cancel", id="cancel"),
            Button("Save", variant="primary", id="save"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            name = self.query_one("#token_name", Input).value.strip()
            val = self.query_one("#token_value", Input).value.strip()
            if name and val:
                self.dismiss((name, val))
            else:
                self.app.notify("Both name and value are required.", severity="error")
        else:
            self.dismiss(None)


class ConfirmDeleteModal(ModalScreen):
    """Screen for confirming server deletion."""

    def __init__(self, server_name: str, **kwargs):
        super().__init__(**kwargs)
        self.server_name = server_name

    CSS = """
    ConfirmDeleteModal {
        align: center middle;
    }
    
    #dialog {
        grid-size: 2;
        grid-gutter: 1;
        grid-rows: 1 3;
        padding: 1 2;
        width: 50;
        height: 11;
        border: thick $error;
        background: $surface;
    }
    
    #dialog-title {
        column-span: 2;
        text-align: center;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield Grid(
            Label(f"Delete '{self.server_name}'?", id="dialog-title"),
            Button("Cancel", id="cancel"),
            Button("Delete", variant="error", id="delete"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete":
            self.dismiss(True)
        else:
            self.dismiss(False)


class MCPManagerApp(App):
    """A Textual app to manage MCP servers."""

    CSS = """
    DataTable {
        height: 100%;
        margin: 1 2;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("s", "sync_now", "Force Sync"),
        Binding("a", "add_server", "Add Server"),
        Binding("e", "edit_config", "Edit Server"),
        Binding("d", "delete_server", "Delete Server"),
        Binding("t", "add_token", "Add Token"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield DataTable(cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "MCP Server Manager"
        self.sub_title = "Manage Cursor and Claude MCPs"

        self.config = ConfigManager.load_master_config()
        self.table = self.query_one(DataTable)

        self.table.add_columns("Status", "Server Name", "Command")
        self.populate_table()

    def populate_table(self):
        self.table.clear()
        servers = self.config.get("mcpServers", {})

        if not servers:
            self.notify("No servers found in ~/.mcp-manager.json")
            return

        for name, details in servers.items():
            is_enabled = details.get("enabled", False)
            status_text = "🟢 Enabled" if is_enabled else "🔴 Disabled"
            command = details.get("command", "")
            if "args" in details and details["args"]:
                command += f" {details['args'][0]}..."

            self.table.add_row(status_text, name, command, key=name)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        server_name = event.row_key.value
        servers = self.config.get("mcpServers", {})
        if server_name in servers:
            current_state = servers[server_name].get("enabled", False)
            new_state = not current_state
            servers[server_name]["enabled"] = new_state

            ConfigManager.save_master_config(self.config)
            ConfigManager.sync_to_apps(self.config)

            self.notify(
                f"{server_name} {'enabled' if new_state else 'disabled'} and synced!"
            )
            self.populate_table()

            row_index = self.table.get_row_index(server_name)
            self.table.move_cursor(row=row_index)

    def action_sync_now(self) -> None:
        ConfigManager.sync_to_apps(self.config)
        self.notify("Forced sync to Claude and Cursor completed.")

    def action_edit_config(self) -> None:
        cursor_coordinate = self.table.cursor_coordinate
        try:
            row_key, _ = self.table.coordinate_to_cell_key(cursor_coordinate)
            server_name = row_key.value
        except Exception:
            self.notify("Please select a server first.", severity="warning")
            return

        servers = self.config.get("mcpServers", {})
        if server_name not in servers:
            self.notify(f"Server {server_name} not found.", severity="error")
            return

        server_config = servers[server_name]
        temp_file = os.path.join(os.getcwd(), f".mcp-edit-{server_name}.json")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(server_config, f, indent=2)
        except Exception as e:
            self.notify(f"Failed to create temp file: {e}", severity="error")
            return

        editor = os.environ.get("EDITOR", "nvim")
        try:
            with self.suspend():
                subprocess.run([editor, temp_file])

            try:
                with open(temp_file, "r", encoding="utf-8") as f:
                    new_config = json.load(f)

                if not isinstance(new_config, dict):
                    self.notify("Invalid format: server configuration must be a JSON object.", severity="error")
                    return

                if "mcpServers" not in self.config:
                    self.config["mcpServers"] = {}
                self.config["mcpServers"][server_name] = new_config

                ConfigManager.save_master_config(self.config)
                ConfigManager.sync_to_apps(self.config)
                self.populate_table()
                self.notify(f"Config for {server_name} updated and synced!")
            except json.JSONDecodeError as jde:
                self.notify(f"Invalid JSON format. Changes not saved: {jde}", severity="error")
            except Exception as e:
                self.notify(f"Failed to read changes: {e}", severity="error")
        finally:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    def action_add_token(self) -> None:
        cursor_coordinate = self.table.cursor_coordinate
        try:
            row_key, _ = self.table.coordinate_to_cell_key(cursor_coordinate)
            server_name = row_key.value
        except Exception:
            self.notify("Please select a server first.", severity="warning")
            return

        def handle_token(token_data):
            if token_data:
                name, val = token_data
                servers = self.config.get("mcpServers", {})
                if server_name in servers:
                    if "env" not in servers[server_name]:
                        servers[server_name]["env"] = {}
                    servers[server_name]["env"][name] = val
                    ConfigManager.save_master_config(self.config)
                    ConfigManager.sync_to_apps(self.config)
                    self.notify(f"Added {name} to {server_name} env & synced!")

        self.push_screen(TokenModal(), handle_token)

    def action_add_server(self) -> None:
        temp_file = os.path.join(os.getcwd(), ".mcp-add-temp.json")
        template = {
            "new-server-name": {
                "enabled": True,
                "command": "command_name",
                "args": [
                    "arg1"
                ],
                "env": {
                    "ENV_VAR": "value"
                }
            }
        }
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(template, f, indent=2)
        except Exception as e:
            self.notify(f"Failed to create template: {e}", severity="error")
            return

        editor = os.environ.get("EDITOR", "nvim")
        try:
            with self.suspend():
                subprocess.run([editor, temp_file])

            try:
                with open(temp_file, "r", encoding="utf-8") as f:
                    new_servers = json.load(f)

                if not isinstance(new_servers, dict):
                    self.notify("Invalid template format: Root must be a JSON object.", severity="error")
                    return

                # Validate and merge servers
                servers = self.config.get("mcpServers", {})
                added_count = 0
                for s_name, s_config in new_servers.items():
                    if s_name == "new-server-name":
                        self.notify("Please change the default 'new-server-name' key.", severity="warning")
                        continue
                    if not isinstance(s_config, dict):
                        self.notify(f"Invalid config format for '{s_name}'. Skipping.", severity="warning")
                        continue
                    
                    servers[s_name] = s_config
                    added_count += 1

                if added_count > 0:
                    self.config["mcpServers"] = servers
                    ConfigManager.save_master_config(self.config)
                    ConfigManager.sync_to_apps(self.config)
                    self.populate_table()
                    self.notify(f"Added {added_count} new server(s) and synced!")
                else:
                    self.notify("No new servers added.")
            except json.JSONDecodeError as jde:
                self.notify(f"Invalid JSON format: {jde}", severity="error")
            except Exception as e:
                self.notify(f"Failed to read template: {e}", severity="error")
        finally:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    def action_delete_server(self) -> None:
        cursor_coordinate = self.table.cursor_coordinate
        try:
            row_key, _ = self.table.coordinate_to_cell_key(cursor_coordinate)
            server_name = row_key.value
        except Exception:
            self.notify("Please select a server to delete.", severity="warning")
            return

        def handle_delete(confirm: bool) -> None:
            if confirm:
                servers = self.config.get("mcpServers", {})
                if server_name in servers:
                    del servers[server_name]
                    ConfigManager.save_master_config(self.config)
                    ConfigManager.sync_to_apps(self.config)
                    self.populate_table()
                    self.notify(f"Server '{server_name}' deleted and synced!")
                else:
                    self.notify(f"Server '{server_name}' not found.", severity="error")

        self.push_screen(ConfirmDeleteModal(server_name), handle_delete)
