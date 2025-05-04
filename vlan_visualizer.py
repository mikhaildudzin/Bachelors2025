import yaml
import re
import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict

def parse_mac_table(file_content):
    """
    Parses the MAC address table from a switch's configuration.

    Args:
        file_content (str): The content of the file.

    Returns:
        dict: A dictionary where keys are MAC addresses and values are dictionaries
              containing 'port' and 'vlan' information.
    """
    mac_table = {}
    try:
        lines = file_content.strip().split('\n')
        # Skip the first line, which is the switch name
        for line in lines[1:]:
            match = re.match(r"([0-9a-fA-F:]+)\s*\(port:\s*(\d+)\)\s*VLAN:\s*(\d+)", line)
            if match:
                mac, port, vlan = match.groups()
                mac_table[mac] = {'port': int(port), 'vlan': int(vlan)}
            else:
                print(f"Warning: Skipping invalid line: {line}")
    except Exception as e:
        print(f"Error parsing MAC table: {e}")
        return {}

    return mac_table

def parse_topology(topology_yaml):
    """
    Parses the network topology from the YAML file.

    Args:
        topology_yaml (str): The content of the topology YAML file.

    Returns:
        list: A list of dictionaries, where each dictionary represents a link
              between two switches.
    """
    try:
        topology_data = yaml.safe_load(topology_yaml)
        if not topology_data or 'links' not in topology_data:
            print("Warning: Topology data is empty or missing 'links' key.")
            return []
        return topology_data['links']
    except yaml.YAMLError as e:
        print(f"Error parsing topology YAML: {e}")
        return []

def build_network_graph(topology, switch_mac_tables):
    """
    Builds a network graph from the topology and MAC address tables using NetworkX.

    Args:
        topology (list): A list of dictionaries representing network links.
        switch_mac_tables (dict): A dictionary of switch MAC address tables.

    Returns:
        nx.Graph: A NetworkX graph representing the network topology.
    """
    graph = nx.Graph()

    for link in topology:
        src_switch = link['src_switch']
        dst_switch = link['dst_switch']
        src_port = link['src_port']
        dst_port = link['dst_port']
        graph.add_edge(src_switch, dst_switch,
                      src_port=src_port, dst_port=dst_port, type='switch')  # Store port info

    # Add end devices from MAC tables
    for switch_name, mac_table_data in switch_mac_tables.items():
        if mac_table_data is None:
            continue
        for mac, mac_info in mac_table_data.items():
            device_name = mac  # Use MAC address as node name
            graph.add_node(device_name, type='end_device', mac=mac, vlan=mac_info['vlan'])
            graph.add_edge(switch_name, device_name, port=mac_info['port'], type='end_device')

    return graph


def detect_vlan_leaks(graph):
    """
    Detects VLAN leaks in the network graph.

    Args:
        graph (nx.Graph): A NetworkX graph representing the network topology.

    Returns:
        dict: A dictionary where keys are MAC addresses and values are lists of
              VLANs the MAC address is seen in.
    """
    vlan_map = defaultdict(set)
    leaks = {}
    for node in graph.nodes():
        if graph.nodes[node].get('type') == 'end_device':
            mac = graph.nodes[node]['mac']
            vlan = graph.nodes[node]['vlan']
            vlan_map[mac].add(vlan)

    for mac, vlan_set in vlan_map.items():
        if len(vlan_set) > 1:
            leaks[mac] = list(vlan_set)
    if not leaks:
        print("No VLAN leaks detected.")
    else:
        print(f"VLAN leaks detected for MAC addresses: {', '.join(leaks.keys())}")
    return leaks


def visualize_network(graph, vlan_leaks):
    """
    Visualizes the network graph using NetworkX and Matplotlib.

    Args:
        graph (nx.Graph): A NetworkX graph representing the network topology.
        vlan_leaks (dict): A dictionary of VLAN leaks.
    """
    # Node colors based on device type and VLAN leakage
    node_colors = []
    for node in graph.nodes():
        if graph.nodes[node].get('type') == 'switch':
            node_colors.append('lightblue')  # Switch
        elif graph.nodes[node].get('type') == 'end_device':
            mac = graph.nodes[node]['mac']
            if mac in vlan_leaks:
                node_colors.append('lightcoral')  # VLAN leak
            else:
                vlan = graph.nodes[node]['vlan']
                # Simple VLAN color mapping (can be expanded)
                vlan_colors = {10: 'lightgreen', 20: 'yellow', 30: 'orange', 40: 'pink', 50: 'cyan', 60: 'magenta', 70: 'gray'}
                node_colors.append(vlan_colors.get(vlan, 'white'))  # Default to white
        else:
            node_colors.append('white')  # Unknown

    # Node labels (shortened MACs)
    node_labels = {node: (node if graph.nodes[node].get('type') == 'switch' else node[:8]) for node in graph.nodes()}

    # Edge labels (port numbers)
    edge_labels = {}
    for u, v, data in graph.edges(data=True):
        if data.get('type') == 'switch':
            edge_labels[(u, v)] = f"S:{data['src_port']}\nD:{data['dst_port']}"
        elif data.get('type') == 'end_device':
            edge_labels[(u, v)] = f"Port:{data['port']}"

    # Layout
    pos = nx.spring_layout(graph)  # You can try different layouts

    # Draw nodes, labels, and edges
    nx.draw_networkx_nodes(graph, pos, node_color=node_colors, node_size=300)
    nx.draw_networkx_labels(graph, pos, labels=node_labels, font_size=8)
    nx.draw_networkx_edges(graph, pos, edge_color='gray', width=1, arrowsize=10)
    nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, font_size=6)

    # Add title and show plot
    plt.title("Network Topology with VLAN Leak Detection")
    plt.show()


if __name__ == "__main__":
    # Load data from files
    try:
        with open("topology.yaml", "r") as f:
            topology_data = f.read()
    except FileNotFoundError:
        print("Error: topology.yaml not found.")
        exit(1)

    # Load switch data
    switch_files = {
        "SW1": "SW1.txt",
        "SW2": "SW2.txt",
        "SW3": "SW3.txt",
        "SW4": "SW4.txt",
        "SW5": "SW5.txt",
    }
    switch_mac_tables = {}
    for switch_name, filename in switch_files.items():
        try:
            with open(filename, "r") as f:
                switch_mac_tables[switch_name] = parse_mac_table(f.read())
        except FileNotFoundError:
            print(f"Error: {filename} not found. Skipping {switch_name}.")
            switch_mac_tables[switch_name] = None
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            switch_mac_tables[switch_name] = None

    # Parse the data
    topology = parse_topology(topology_data)
    network_graph = build_network_graph(topology, switch_mac_tables)
    vlan_leaks = detect_vlan_leaks(network_graph)

    # Visualize the network
    visualize_network(network_graph, vlan_leaks)
