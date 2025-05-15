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
MAC_TABLE_DIR = '.' # Directory where MAC address table .txt files are located
LOG_LEVEL = logging.INFO # Change to logging.DEBUG for more verbose output

# Setup logging
logging.basicConfig(level=LOG_LEVEL, format='%(levelname)s: %(message)s')

# ==============================
# Helper Functions
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
                return None, {} # Return None for topology_data, empty dict for connections
    except FileNotFoundError:
        logging.error(f"Topology file '{filename}' not found.")
        return None, {}
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML file '{filename}': {e}")
        return None, {}

    switch_connections = {}
    # Ensure 'links' key exists and is a list
    for link in topology_data.get('links', []):
        try:
            # Ensure all required keys are present in the link
            source_switch = link['source']
            dest_switch = link['destination']
            # Convert port numbers to integers for consistency
            source_port = int(link['source_port'])
            dest_port = int(link['destination_port'])
            
            switch_connections[(source_switch, source_port)] = (dest_switch, dest_port)
            switch_connections[(dest_switch, dest_port)] = (source_switch, source_port)
        except (KeyError, ValueError) as e:
            logging.warning(f"Skipping invalid link entry: {link}. Error: {e}. Ensure 'source', 'destination', 'source_port', 'destination_port' are present and ports are numeric.")
    
    logging.info(f"Loaded switch connections: {switch_connections}")
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
                        # Example line format: "00:0a:95:11:22:33 dynamic (port: 1) VLAN: 10"
                        if '(port:' in line and 'VLAN:' in line: # Basic check for relevant lines
                            parts = line.strip().split()
                            try:
                                mac_address = parts[0]
                                # Find port: parts[i] == '(port:', port is parts[i+1].strip(')')
                                # Find vlan: parts[j] == 'VLAN:', vlan is parts[j+1]
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
                logging.debug(f"  MAC {mac}: VLANs are NOT same: {[loc[2] for loc in locations]}")
                # Potential VLAN leak. Filter inter-switch links; if MAC on such a link, switch is leaking.
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
        elif locations: # Original locations existed, but all were filtered out
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

    # Add switch nodes
    for switch in topology_data.get('switches', []):
        switch_name = switch.get('name')
        if not switch_name:
            logging.warning(f"Skipping switch with no name: {switch}")
            continue
        color = 'red' if switch_name in leaking_switches else 'skyblue' # Changed lightblue to skyblue for better contrast
        G.add_node(switch_name, type='switch', color=color, label=switch_name)

    # Add links between switches (edges)
    # Iterate through unique links to avoid duplicate edges if switch_connections is symmetrical
    added_edges = set()
    for (src, src_port), (dst, dst_port) in switch_connections.items():
        # Ensure canonical representation of edge to add only once
        edge = tuple(sorted((src, dst)))
        if edge not in added_edges:
            G.add_edge(src, dst, label=f'P{src_port}<->P{dst_port}', color='gray')
            added_edges.add(edge)

    # Add device nodes and edges to their connected switch
    # Use a list of distinct colors for VLANs
    distinct_colors = list(mcolors.TABLEAU_COLORS.values()) # Using Tableau colors for better distinction

    for mac, locations in device_locations.items():
        for switch_name, port_str, vlan in locations:
            # Check if this device connection is on an inter-switch link port.
            # Ports in switch_connections are integers.
            is_on_trunk = False
            try:
                port_int = int(port_str)
                if (switch_name, port_int) in switch_connections:
                    logging.debug(f"Device {mac} on ({switch_name}, port {port_str}, VLAN {vlan}) appears on an inter-switch link. Not adding separate device edge.")
                    is_on_trunk = True 
            except ValueError:
                # Port_str is not an integer (e.g. "Port-channel1"), assume it's an access port.
                pass # is_on_trunk remains False

            if not is_on_trunk:
                if not G.has_node(mac): # Add device node only once
                     G.add_node(mac, type='device', label=f"{mac}\n(VLAN {vlan})") # Add VLAN to device label
                
                # Assign color based on VLAN
                try:
                    vlan_int_for_color = int(vlan)
                    edge_color = distinct_colors[vlan_int_for_color % len(distinct_colors)]
                except ValueError:
                    edge_color = 'lightgrey' # Default color for non-integer VLANs
                    logging.warning(f"VLAN '{vlan}' for MAC {mac} is not an integer. Using default color for edge.")

                if G.has_node(switch_name): # Ensure switch node exists
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

    plt.figure(figsize=(16, 12)) # Increased figure size

    # Prepare node colors and sizes
    node_colors = []
    node_sizes = []
    node_labels = {}

    for node, data in G.nodes(data=True):
        node_labels[node] = data.get('label', node) # Use custom label if present
        if data.get('type') == 'switch':
            node_colors.append(data.get('color', 'skyblue'))
            node_sizes.append(3000)
        elif data.get('type') == 'device':
            node_colors.append('lightgreen') # Color for device nodes
            node_sizes.append(1500)
        else:
            node_colors.append('gray') # Default
            node_sizes.append(1000)

    # Prepare edge colors
    edge_colors = [G[u][v].get('color', 'gray') for u, v in G.edges()]

    # Use a layout that tries to minimize edge crossing
    pos = nx.kamada_kawai_layout(G) # Alternative: nx.spring_layout(G, k=0.5, iterations=50)

    nx.draw(G, pos, 
            labels=node_labels, 
            with_labels=True, 
            node_color=node_colors, 
            node_size=node_sizes,
            edge_color=edge_colors, 
            width=1.5, # Edge width
            font_size=8,
            font_weight='bold')

    edge_labels = nx.get_edge_attributes(G, 'label')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=7)

    # Create legend for VLANs based on actual device connections
    # Use colors from distinct_colors list
    distinct_colors_list = list(mcolors.TABLEAU_COLORS.values())
    vlan_legend_handles = []
    seen_vlans_for_legend = set()

    for mac, locs in device_locations.items():
        for _, _, vlan_str in locs:
            if vlan_str not in seen_vlans_for_legend:
                try:
                    vlan_int = int(vlan_str)
                    color = distinct_colors_list[vlan_int % len(distinct_colors_list)]
                    vlan_legend_handles.append(plt.Line2D([0], [0], marker='o', color='w', label=f'VLAN {vlan_str}',
                                                          markerfacecolor=color, markersize=10))
                    seen_vlans_for_legend.add(vlan_str)
                except ValueError:
                    pass # Skip non-integer VLANs for color legend

    if vlan_legend_handles:
        plt.legend(handles=vlan_legend_handles, title="VLAN Colors (Devices)", loc="upper left", bbox_to_anchor=(1.05, 1))
    
    plt.title('Network Topology with VLAN Leak Detection', size=16)
    plt.axis('off') # Turn off axis
    #plt.tight_layout() # Adjust layout to prevent labels from overlapping
    plt.show()

# ==============================
# Main Execution
# ==============================
def main():
    """
    Main function to run the network analysis and visualization.
    """
    # STEP 1: Load Topology Data
    topology, switch_connections = load_topology(TOPOLOGY_FILE)
    if topology is None: # Critical error, cannot proceed
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
