import os
import yaml
import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict
import matplotlib.colors as mcolors
import logging

# ==============================
# Configuration
# ==============================
TOPOLOGY_FILE = 'topology.yaml'
MAC_TABLE_DIR = '.'
LOG_LEVEL = logging.INFO

logging.basicConfig(level=LOG_LEVEL, format='%(levelname)s: %(message)s')

# ==============================
# Functions
# ==============================

def load_topology(filename):
    """
    Loads network topology data from a YAML file.
    Converts port numbers to integers.
    """
    try:
        with open(filename, 'r') as file:
            topology_data = yaml.safe_load(file)
            if not topology_data:
                logging.error(f"Topology file '{filename}' is empty or invalid.")
                return None, {}
    except FileNotFoundError:
        logging.error(f"Topology file '{filename}' not found.")
        return None, {}
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML file '{filename}': {e}")
        return None, {}

    switch_connections = {}
    for link in topology_data.get('links', []):
        try:
            source_switch = link['source']
            dest_switch = link['destination']
            source_port = int(link['source_port'])
            dest_port = int(link['destination_port'])
            
            switch_connections[(source_switch, source_port)] = (dest_switch, dest_port)
            switch_connections[(dest_switch, dest_port)] = (source_switch, source_port)
        except (KeyError, ValueError) as e:
            logging.warning(f"Skipping invalid link entry: {link}. Error: {e}. Ensure 'source', 'destination', 'source_port', 'destination_port' are present and ports are numeric.")
    
    return topology_data, switch_connections

def parse_mac_tables(directory, topology_filename):
    """
    Parses MAC address table files from a given directory.
    MAC table files should be .txt and not the topology file itself.
    """
    mac_tables = defaultdict(list)
    if not os.path.isdir(directory):
        logging.error(f"MAC address table directory '{directory}' not found.")
        return mac_tables

    for filename in os.listdir(directory):
        if filename.endswith('.txt') and filename != os.path.basename(topology_filename):
            switch_name = filename.replace('.txt', '')
            filepath = os.path.join(directory, filename)
            try:
                with open(filepath, 'r') as f:
                    for line in f:
                        if '(port:' in line and 'VLAN:' in line:
                            parts = line.strip().split()
                            try:
                                mac_address = parts[0]
                                port_index = -1
                                vlan_index = -1
                                for i, part in enumerate(parts):
                                    if part == '(port:':
                                        port_index = i + 1
                                    elif part == 'VLAN:':
                                        vlan_index = i + 1
                                
                                if port_index != -1 and port_index < len(parts) and \
                                   vlan_index != -1 and vlan_index < len(parts):
                                    port = parts[port_index].strip(')')
                                    vlan = parts[vlan_index]
                                    mac_tables[mac_address].append((switch_name, port, vlan))
                                else:
                                    logging.warning(f"Could not parse port/VLAN from line in '{filename}': {line.strip()}")

                            except IndexError:
                                logging.warning(f"Malformed line in '{filename}': {line.strip()}")
            except IOError as e:
                logging.error(f"Could not read file '{filepath}': {e}")
    
    logging.debug(f"Parsed MAC tables: {dict(mac_tables)}")
    return mac_tables

def detect_vlan_leaks_and_identify_devices(mac_tables, switch_connections):
    """
    Detects VLAN leaks and identifies device locations (access ports).
    Ports in switch_connections are expected to be integers.
    Ports from MAC tables are strings and will be converted for lookups.
    """
    leaking_switches = set()
    device_locations = defaultdict(list)

    for mac, locations in mac_tables.items():
        logging.debug(f"\nProcessing MAC: {mac}, Original Locations: {locations}")
        
        processed_locations_for_mac = []

        if not locations:
            continue

        if len(locations) == 1:
            # MAC seen in one location, assume it's an access port.
            # Port here is still a string, which is fine for device_locations.
            logging.debug(f"  MAC {mac} seen in a single location. Treating as access port: {locations[0]}")
            processed_locations_for_mac = locations
        else: # MAC seen in multiple locations
            first_vlan = locations[0][2]
            all_same_vlan = all(loc[2] == first_vlan for loc in locations)
            
            temp_locations = []
            if all_same_vlan:
                logging.debug(f"  MAC {mac}: All locations have the same VLAN: {first_vlan}.")
                # Filter out inter-switch links.
                for switch_name, port_str, vlan_val in locations:
                    try:
                        port_int = int(port_str)
                        connection_key = (switch_name, port_int)
                    except ValueError: # Port is not a simple integer (e.g., "Port-channel1")
                        logging.debug(f"    Port '{port_str}' on switch '{switch_name}' is non-numeric. Assuming access port.")
                        temp_locations.append((switch_name, port_str, vlan_val))
                        continue
                    
                    if connection_key in switch_connections:
                        logging.debug(f"    Switch-port {connection_key} (orig port '{port_str}') is inter-switch. Ignoring for device location.")
                    else:
                        logging.debug(f"    Switch-port {connection_key} (orig port '{port_str}') is access port.")
                        temp_locations.append((switch_name, port_str, vlan_val))
            else: # VLANs are not the same across locations for this MAC
                logging.info(f"  MAC {mac}: VLANs are NOT same: {[loc[2] for loc in locations]}")
                for switch_name, port_str, vlan_val in locations:
                    logging.debug(f"    Checking switch-port ({switch_name}, {port_str}) with VLAN {vlan_val}")
                    try:
                        port_int = int(port_str)
                        connection_key = (switch_name, port_int)
                    except ValueError:
                        logging.debug(f"      Port '{port_str}' on switch '{switch_name}' non-numeric. Assuming access port.")
                        temp_locations.append((switch_name, port_str, vlan_val))
                        continue

                    if connection_key in switch_connections:
                        logging.debug(f"      Switch-port {connection_key} (orig port '{port_str}') is inter-switch.")
                        leaking_switches.add(switch_name)
                        logging.info(f"      VLAN leak detected: MAC {mac} (VLAN {vlan_val}) on inter-switch link {connection_key}. Switch '{switch_name}' marked as leaking.")
                    else:
                        logging.debug(f"      Switch-port {connection_key} (orig port '{port_str}') is access port.")
                        temp_locations.append((switch_name, port_str, vlan_val))
            processed_locations_for_mac = temp_locations

        if processed_locations_for_mac:
            final_vlans = set(loc[2] for loc in processed_locations_for_mac)
            if len(final_vlans) > 1:
                logging.warning(f"  MAC {mac}: After filtering, device appears on access ports with multiple VLANs: {final_vlans}. Locations: {processed_locations_for_mac}")
            device_locations[mac].extend(processed_locations_for_mac)
        elif locations: 
             logging.debug(f"  MAC {mac}: All original locations were filtered out (e.g., all were inter-switch links).")

    return leaking_switches, device_locations

def build_network_graph(topology_data, switch_connections, device_locations, leaking_switches):
    """
    Builds a NetworkX graph from topology, device locations, and leaking switch information.
    """
    G = nx.Graph()
    if not topology_data or 'switches' not in topology_data :
        logging.error("Cannot build graph: Topology data or switches list is missing.")
        return G

    for switch in topology_data.get('switches', []):
        switch_name = switch.get('name')
        if not switch_name:
            logging.warning(f"Skipping switch with no name: {switch}")
            continue
        color = 'red' if switch_name in leaking_switches else 'skyblue'
        G.add_node(switch_name, type='switch', color=color, label=switch_name)

    added_edges = set()
    for (src, src_port), (dst, dst_port) in switch_connections.items():
        edge = tuple(sorted((src, dst)))
        if edge not in added_edges:
            G.add_edge(src, dst, label=f'P{src_port}<->P{dst_port}', color='gray')
            added_edges.add(edge)

    # --- VLAN to color mapping ---
    vlan_set = set()
    for mac, locations in device_locations.items():
        for _, _, vlan in locations:
            vlan_set.add(vlan)
    vlan_list = sorted(vlan_set, key=lambda x: int(x) if x.isdigit() else x)
    color_palette = list(mcolors.TABLEAU_COLORS.values()) + \
                    list(mcolors.CSS4_COLORS.values()) + \
                    list(mcolors.XKCD_COLORS.values())
    color_palette = list(dict.fromkeys(color_palette))
    vlan_to_color = {}
    for idx, vlan in enumerate(vlan_list):
        vlan_to_color[vlan] = color_palette[idx % len(color_palette)]

    for mac, locations in device_locations.items():
        for switch_name, port_str, vlan in locations:
            is_on_trunk = False
            try:
                port_int = int(port_str)
                if (switch_name, port_int) in switch_connections:
                    logging.debug(f"Device {mac} on ({switch_name}, port {port_str}, VLAN {vlan}) appears on an inter-switch link. Not adding separate device edge.")
                    is_on_trunk = True 
            except ValueError:
                pass

            if not is_on_trunk:
                if not G.has_node(mac):
                    node_color = vlan_to_color.get(vlan, 'lightgrey')
                    G.add_node(mac, type='device', label=f"{mac}\n(VLAN {vlan})", color=node_color)
                edge_color = vlan_to_color.get(vlan, 'lightgrey')
                if G.has_node(switch_name):
                    G.add_edge(switch_name, mac, label=f'P{port_str}\nVLAN {vlan}', color=edge_color)
                else:
                    logging.warning(f"Switch '{switch_name}' for MAC {mac} not found in graph nodes. Skipping edge.")
    return G

def visualize_network(G, device_locations):
    """
    Visualizes the network graph using Matplotlib.
    """
    if not G.nodes:
        logging.info("Graph is empty. Nothing to visualize.")
        return

    plt.figure(figsize=(16, 12))

    node_colors = []
    node_sizes = []
    node_labels = {}

    for node, data in G.nodes(data=True):
        node_labels[node] = data.get('label', node)
        if data.get('type') == 'switch':
            node_colors.append(data.get('color', 'skyblue'))
            node_sizes.append(3000)
        elif data.get('type') == 'device':
            node_colors.append(data.get('color', 'lightgreen')) 
            node_sizes.append(1500)
        else:
            node_colors.append('gray')
            node_sizes.append(1000)

    edge_colors = [G[u][v].get('color', 'gray') for u, v in G.edges()]

    pos = nx.kamada_kawai_layout(G)

    nx.draw(G, pos, 
            labels=node_labels, 
            with_labels=True, 
            node_color=node_colors, 
            node_size=node_sizes,
            edge_color=edge_colors, 
            width=1.5,
            font_size=8,
            font_weight='bold')

    edge_labels = nx.get_edge_attributes(G, 'label')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=7)

    vlan_legend_handles = []
    seen_vlans = set()
    for node, data in G.nodes(data=True):
        if data.get('type') == 'device':
            label = data.get('label', '')
            vlan = label.split('VLAN')[-1].strip(' )(') if 'VLAN' in label else None
            color = data.get('color', 'lightgrey')
            if vlan and vlan not in seen_vlans:
                vlan_legend_handles.append(
                    plt.Line2D([0], [0], marker='o', color='w', label=f'VLAN {vlan}',
                               markerfacecolor=color, markersize=10)
                )
                seen_vlans.add(vlan)
    if vlan_legend_handles:
        plt.legend(handles=vlan_legend_handles, title="VLAN Colors (Devices)", loc="upper left", bbox_to_anchor=(1.05, 1))

    plt.title('Network Topology with VLAN Leak Detection', size=16)
    plt.axis('off')
    plt.show()

def main():
    """
    Main function to run the network analysis and visualization.
    """
    # STEP 1: Load Topology Data
    topology, switch_connections = load_topology(TOPOLOGY_FILE)
    if topology is None: 
        return

    # STEP 2: Parse MAC Tables
    mac_tables = parse_mac_tables(MAC_TABLE_DIR, TOPOLOGY_FILE)
    if not mac_tables:
        logging.warning("No MAC address information found or parsed. Visualization might be limited.")

    # STEP 3: Detect VLAN Leaks and Identify Device Locations
    leaking_switches, device_locations = detect_vlan_leaks_and_identify_devices(mac_tables, switch_connections)
    
    logging.info("\n==============================")
    logging.info("Analysis Results:")
    logging.info("==============================")
    logging.info(f"Leaking Switches: {leaking_switches if leaking_switches else 'None'}")
    logging.info("Device Locations (MAC: [(Switch, Port, VLAN), ...]):")
    if device_locations:
        for mac_addr, locs in device_locations.items():
            logging.info(f"  {mac_addr}: {locs}")
    else:
        logging.info("  No device locations determined.")

    # STEP 4: Build Graph Topology
    network_graph = build_network_graph(topology, switch_connections, device_locations, leaking_switches)

    # STEP 5: Visualize the Network
    visualize_network(network_graph, device_locations)

if __name__ == "__main__":
    main()
