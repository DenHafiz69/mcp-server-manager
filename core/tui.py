import subprocess
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
        Binding("e", "edit_config", "Edit Config (nvim)"),
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
        with self.suspend():
            subprocess.run(["nvim", MASTER_CONFIG_PATH])
        self.config = ConfigManager.load_master_config()
        ConfigManager.sync_to_apps(self.config)
        self.populate_table()
        self.notify("Config reloaded from disk & synced!")

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
