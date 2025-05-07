import yaml
import os
import re
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

def parse_mac_tables(mac_table_dir):
    """
    Parses MAC address tables from files in a directory.

    Args:
        mac_table_dir (str): Path to the directory containing MAC table files.

    Returns:
        dict: A dictionary where keys are switch names and values are lists of
              dictionaries, each containing 'mac_address', 'vlan', and 'port'.
    """

    mac_tables = {}
    for filename in os.listdir(mac_table_dir):
        if filename.startswith("SW") and filename.endswith(".txt"):
            print(f"Parsing MAC table from {filename}")
            switch_name = filename[:-4]  # Remove ".txt"
            mac_tables[switch_name] = []
            with open(os.path.join(mac_table_dir, filename), "r") as f:
                for line in f:
                    match = re.search(r"([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})\s+\(port:\s+(\d+)\)\s+VLAN:\s+(\d+)", line)
                    print(match)
                    if match:
                        mac_address = match.group(1)
                        vlan = int(match.group(2))
                        port = int(match.group(3))
                        mac_tables[switch_name].append({
                            "mac_address": mac_address,
                            "vlan": vlan,
                            "port": port,
                        })
    
    return mac_tables


def load_topology(topology_file):
    """
    Loads the network topology from a YAML file.

    Args:
        topology_file (str): Path to the YAML file containing the topology.

    Returns:
        dict: A dictionary representing the network topology.
    """

    with open(topology_file, "r") as f:
        topology = yaml.safe_load(f)
    return topology


def build_graph(topology, mac_tables):
    """
    Builds a NetworkX graph from the topology and MAC address tables.

    Args:
        topology (dict): The network topology dictionary.
        mac_tables (dict): The MAC address tables dictionary.

    Returns:
        networkx.Graph: The NetworkX graph representing the network.
    """

    graph = nx.Graph()

    # Add switch nodes
    for link in topology["links"]:
        src_switch = link["src_switch"]
        dst_switch = link["dst_switch"]
        if src_switch not in graph:
            graph.add_node(src_switch, type="switch")
        if dst_switch not in graph:
            graph.add_node(dst_switch, type="switch")
        graph.add_edge(src_switch, dst_switch,
                      src_port=link["src_port"], dst_port=link["dst_port"])

    # Add end devices from MAC tables
    vlan_colors = {}
    next_color_index = 0
    colors = list(mcolors.TABLEAU_COLORS.values())  # Use Tableau Colors for distinctiveness

    for switch, entries in mac_tables.items():
        for entry in entries:
            mac_address = entry["mac_address"]
            vlan = entry["vlan"]
            port = entry["port"]

            device_name = f"Device-{mac_address[-4:]}"  # Use last 4 digits for name

            graph.add_node(device_name,
                           type="device",
                           mac_address=mac_address,
                           vlan=vlan)

            graph.add_edge(switch, device_name, port=port)

            # Assign colors based on VLAN
            if vlan not in vlan_colors:
                vlan_colors[vlan] = colors[next_color_index % len(colors)]
                next_color_index += 1

    # Detect VLAN leakage
    mac_vlan_map = {}
    for node, attrs in graph.nodes(data=True):
        if attrs.get("type") == "device":
            mac = attrs["mac_address"]
            vlan = attrs["vlan"]
            if mac not in mac_vlan_map:
                mac_vlan_map[mac] = set()
            mac_vlan_map[mac].add(vlan)

    leaky_macs = {mac: vlans for mac, vlans in mac_vlan_map.items() if len(vlans) > 1}
    for node, attrs in graph.nodes(data=True):
        if attrs.get("type") == "device" and attrs["mac_address"] in leaky_macs:
            attrs["leaky_vlans"] = leaky_macs[attrs["mac_address"]]

    return graph, vlan_colors


def visualize_network(graph, vlan_colors):
    """
    Visualizes the network graph.

    Args:
        graph (networkx.Graph): The network graph.
        vlan_colors (dict):  Mapping of VLANs to colors.
    """

    pos = nx.spring_layout(graph, k=0.3, iterations=50)  # Adjust layout parameters as needed

    # Node colors and sizes
    node_colors = []
    node_sizes = []
    node_borders = []
    for node, attrs in graph.nodes(data=True):
        if attrs.get("type") == "switch":
            node_colors.append("lightblue")
            node_sizes.append(800)
            node_borders.append("black")
        elif attrs.get("type") == "device":
            vlan = attrs["vlan"]
            node_colors.append(vlan_colors.get(vlan, "gray"))  # Default to gray if VLAN not found
            node_sizes.append(400)
            if "leaky_vlans" in attrs:
                node_borders.append("red")  # Red border for leaky devices
            else:
                node_borders.append("black")
        else:
            node_colors.append("gray")
            node_sizes.append(200)
            node_borders.append("black")

    nx.draw(graph, pos,
            with_labels=True,
            node_color=node_colors,
            node_size=node_sizes,
            edgecolors=node_borders,
            linewidths=2,
            font_size=8)

    # Edge labels (port numbers)
    edge_labels = {}
    for u, v, data in graph.edges(data=True):
        label = ""
        if "src_port" in data and "dst_port" in data:
            label = f"{data['src_port']}-{data['dst_port']}"
        elif "port" in data:
            label = str(data["port"])
        edge_labels[(u, v)] = label
    nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, font_size=6)

    # Node tooltips (using matplotlib annotations - limited interactivity)
    for node, (x, y) in pos.items():
        attrs = graph.nodes[node]
        if attrs.get("type") == "device":
            tooltip = f"MAC: {attrs['mac_address']}\nVLAN: {attrs['vlan']}"
            if "leaky_vlans" in attrs:
                tooltip += f"\nLeakage: {attrs['leaky_vlans']}"
            plt.annotate(tooltip, xy=(x, y), xytext=(x + 0.05, y + 0.05),
                         bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.5),
                         fontsize=6, ha="left", va="bottom")

    plt.title("Network Topology Visualization")
    plt.show()


if __name__ == "__main__":
    topology_file = "topology.yaml"
    mac_table_dir = "mac_results"  # Replace with your actual directory

    mac_tables = parse_mac_tables(mac_table_dir)
    topology = load_topology(topology_file)
    graph, vlan_colors = build_graph(topology, mac_tables)
    visualize_network(graph, vlan_colors)