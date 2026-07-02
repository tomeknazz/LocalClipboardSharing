import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import threading
from typing import Optional
from clipboard_logic import ClipboardShareApp, Peer
import argparse
from pathlib import Path


class ClipboardAppGui:
    """
    Provides the Tkinter-based GUI for the clipboard sharing application.
    ...
    """
    def __init__(self, root, args):
        self.root = root
        self.root.title("Clipboard Sharing")
        self.args = args

        self.app = None
        self.app_thread = None

        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky="nsew")

        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        # Peer list
        self.peer_frame = ttk.LabelFrame(self.main_frame, text="Peers")
        self.peer_frame.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)
        self.peer_frame.rowconfigure(0, weight=1)
        self.peer_frame.columnconfigure(0, weight=1)

        self.peer_list = ttk.Treeview(self.peer_frame, columns=("peer", "status", "active"), show="headings")
        self.peer_list.heading("peer", text="Peer")
        self.peer_list.heading("status", text="Status")
        self.peer_list.heading("active", text="Active")
        self.peer_list.grid(row=0, column=0, sticky="nsew")
        self.peer_list.bind("<<TreeviewSelect>>", self._on_peer_select)

        # Peer modification buttons
        self.peer_buttons_frame = ttk.Frame(self.main_frame)
        self.peer_buttons_frame.grid(row=1, column=0, columnspan=3, sticky="w", padx=5, pady=5)

        self.edit_peer_button = ttk.Button(self.peer_buttons_frame, text="Edit Peer", command=self.edit_peer, state=tk.DISABLED)
        self.edit_peer_button.pack(side="left", padx=(0, 5))
        self.remove_peer_button = ttk.Button(self.peer_buttons_frame, text="Remove Peer", command=self.remove_peer, state=tk.DISABLED)
        self.remove_peer_button.pack(side="left", padx=5)
        self.toggle_active_button = ttk.Button(self.peer_buttons_frame, text="Toggle Active", command=self.toggle_peer_active, state=tk.DISABLED)
        self.toggle_active_button.pack(side="left", padx=5)

        # Add Peer
        self.add_peer_frame = ttk.Frame(self.main_frame)
        self.add_peer_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=5, pady=5)
        
        self.new_peer_var = tk.StringVar()
        self.new_peer_entry = ttk.Entry(self.add_peer_frame, textvariable=self.new_peer_var)
        self.new_peer_entry.pack(side="left", fill="x", expand=True)
        self.add_peer_button = ttk.Button(self.add_peer_frame, text="Add Peer Manually", command=self.add_peer)
        self.add_peer_button.pack(side="left", padx=5)

        # Discovered Peers
        self.discovered_frame = ttk.LabelFrame(self.main_frame, text="Discovered Peers")
        self.discovered_frame.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)
        self.discovered_frame.rowconfigure(0, weight=1)
        self.discovered_frame.columnconfigure(0, weight=1)

        self.discovered_list = ttk.Treeview(self.discovered_frame, columns=("peer",), show="headings")
        self.discovered_list.heading("peer", text="Discovered Peer")
        self.discovered_list.grid(row=0, column=0, sticky="nsew")
        self.discovered_list.bind("<<TreeviewSelect>>", self._on_discovered_peer_select)
        
        self.add_discovered_button = ttk.Button(self.discovered_frame, text="Add Selected Peer", command=self.add_discovered_peer, state=tk.DISABLED)
        self.add_discovered_button.grid(row=1, column=0, pady=5)

        # Status and Control
        self.status_var = tk.StringVar()
        self.status_bar = ttk.Label(self.main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        self.status_bar.grid(row=4, column=0, columnspan=3, sticky="ew", padx=5, pady=5)

        self.start_button = ttk.Button(self.main_frame, text="Start", command=self.start_app)
        self.start_button.grid(row=5, column=0, padx=5, pady=5)
        self.stop_button = ttk.Button(self.main_frame, text="Stop", command=self.stop_app, state=tk.DISABLED)
        self.stop_button.grid(row=5, column=1, padx=5, pady=5)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.update_peer_list()
        self.update_discovered_peers_list()

    def _get_selected_peer(self, from_discovered=False) -> Optional[Peer]:
        tree = self.discovered_list if from_discovered else self.peer_list
        selection = tree.selection()
        if not selection:
            return None
        
        item = tree.item(selection[0])
        peer_str = item["values"][0]
        host, port_str = peer_str.rsplit(":", 1)
        port = int(port_str)
        return Peer(host, port)

    def _on_peer_select(self, event=None):
        is_peer_selected = bool(self.peer_list.selection())
        state = tk.NORMAL if is_peer_selected and self.app else tk.DISABLED
        self.edit_peer_button.config(state=state)
        self.remove_peer_button.config(state=state)
        self.toggle_active_button.config(state=state)

    def _on_discovered_peer_select(self, event=None):
        is_peer_selected = bool(self.discovered_list.selection())
        state = tk.NORMAL if is_peer_selected and self.app else tk.DISABLED
        self.add_discovered_button.config(state=state)

    def start_app(self):
        # ... (same as before)
        self.update_discovered_peers_list()

    def stop_app(self):
        # ... (same as before)
        self.update_discovered_peers_list()

    def add_discovered_peer(self):
        peer = self._get_selected_peer(from_discovered=True)
        if not peer:
            return
        
        if self.app:
            self.app.add_peer(peer, is_active=False)
            # The callback will trigger the list updates
        else:
            messagebox.showwarning("Not Running", "Cannot add a peer while the application is not running.")

    def update_discovered_peers_list(self):
        for i in self.discovered_list.get_children():
            self.discovered_list.delete(i)
        
        if self.app:
            discovered_peers = self.app.get_discovered_peers()
            for peer in discovered_peers:
                self.discovered_list.insert("", "end", values=(f"{peer.host}:{peer.port}",))
        self._on_discovered_peer_select()

    def handle_app_callback(self, event, data):
        if event == "UPDATE_PEERS":
            self.root.after(0, self.update_peer_list)
            self.root.after(0, self.update_discovered_peers_list) # Also update discovered list
        elif event == "UPDATE_STATUS":
            self.root.after(0, self.update_peer_list)
        elif event == "UPDATE_DISCOVERED_PEERS":
            self.root.after(0, self.update_discovered_peers_list)
        elif event == "RECEIVED":
            self.root.after(0, self.status_var.set, data)
    
    # ... (rest of the methods are mostly the same)
    def _on_peer_select(self, event=None):
        is_peer_selected = bool(self.peer_list.selection())
        state = tk.NORMAL if is_peer_selected else tk.DISABLED
        self.edit_peer_button.config(state=state)
        self.remove_peer_button.config(state=state)
        self.toggle_active_button.config(state=state)

    def start_app(self):
        self.app = ClipboardShareApp(
            listen_port=self.args.listen_port,
            peers=self.args.peer,
            log_file=Path(self.args.log_file),
            poll_interval=self.args.poll_interval,
            gui_callback=self.handle_app_callback
        )
        self.app_thread = threading.Thread(target=self.app.run, daemon=True)
        self.app_thread.start()

        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.add_peer_button.config(state=tk.NORMAL)
        self.status_var.set(f"Running on port {self.args.listen_port}")
        self.update_peer_list()
        self.update_discovered_peers_list()
        self._on_peer_select()
        self._on_discovered_peer_select()

    def stop_app(self):
        if self.app:
            self.app.stop()
        self.app_thread = None
        self.app = None

        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.add_peer_button.config(state=tk.NORMAL)
        self.status_var.set("Stopped")
        self.update_peer_list()
        self.update_discovered_peers_list()
        self._on_peer_select()
        self._on_discovered_peer_select()

    def add_peer(self):
        peer_str = self.new_peer_var.get()
        if not peer_str:
            return

        try:
            host, port_str = peer_str.rsplit(":", 1)
            port = int(port_str)
            if not (1 <= port <= 65535):
                raise ValueError("Port out of range")
            new_peer = Peer(host, port)
        except ValueError:
            messagebox.showerror("Invalid Peer", "Invalid peer format. Use HOST:PORT.")
            return

        target_peers = []
        if self.app:
            with self.app.peer_lock:
                target_peers = self.app.peers
        else:
            target_peers = self.args.peer

        if new_peer in target_peers:
            messagebox.showinfo("Peer Exists", "This peer is already in the list.")
            return

        if self.app:
            self.app.add_peer(new_peer, is_active=True)
        else:
            self.args.peer.append(new_peer)
            self.update_peer_list()
        self.new_peer_var.set("")

    def edit_peer(self):
        old_peer = self._get_selected_peer()
        if not old_peer:
            return

        new_peer_str = simpledialog.askstring(
            "Edit Peer", "Enter new peer address (HOST:PORT):",
            initialvalue=f"{old_peer.host}:{old_peer.port}"
        )
        if not new_peer_str:
            return

        try:
            host, port_str = new_peer_str.rsplit(":", 1)
            port = int(port_str)
            if not (1 <= port <= 65535):
                raise ValueError("Port out of range")
            new_peer = Peer(host, port)
        except ValueError:
            messagebox.showerror("Invalid Peer", "Invalid peer format. Use HOST:PORT.")
            return

        if self.app:
            self.app.update_peer(old_peer, new_peer)
        else:
            if new_peer not in self.args.peer:
                index = self.args.peer.index(old_peer)
                self.args.peer[index] = new_peer
                self.update_peer_list()
            else:
                messagebox.showinfo("Peer Exists", "This peer is already in the list.")

    def remove_peer(self):
        peer_to_remove = self._get_selected_peer()
        if not peer_to_remove:
            return
        
        if messagebox.askyesno("Remove Peer", f"Are you sure you want to remove {peer_to_remove.host}:{peer_to_remove.port}?"):
            if self.app:
                self.app.remove_peer(peer_to_remove)
            else:
                self.args.peer.remove(peer_to_remove)
                self.update_peer_list()

    def toggle_peer_active(self):
        peer = self._get_selected_peer()
        if not peer:
            return
        
        if self.app:
            self.app.toggle_peer_active(peer)
        else:
            messagebox.showwarning("Not Running", "Cannot toggle peer status while the application is not running.")


    def update_peer_list(self):
        for i in self.peer_list.get_children():
            self.peer_list.delete(i)
        
        if self.app:
            peer_info = self.app.get_peer_info_for_gui()
            for peer, status, is_active in peer_info:
                active_str = "Yes" if is_active else "No"
                self.peer_list.insert("", "end", values=(f"{peer.host}:{peer.port}", status, active_str))
        else:
            for peer in self.args.peer:
                self.peer_list.insert("", "end", values=(f"{peer.host}:{peer.port}", "Not Running", "N/A"))

        self._on_peer_select()
    
    def on_closing(self):
        if self.app and messagebox.askokcancel("Quit", "Do you want to quit?"):
            self.stop_app()
            self.root.destroy()
        elif not self.app:
            self.root.destroy()


def run_gui(args):
    root = tk.Tk()
    app_gui = ClipboardAppGui(root, args)
    root.mainloop()
