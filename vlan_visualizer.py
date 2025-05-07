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
            switch_name = filename[:-4]  # Remove ".txt"
            mac_tables[switch_name] = []
            with open(os.path.join(mac_table_dir, filename), "r") as f:
                for line in f:
                    match = re.search(r"([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})\s+\(port:\s+(\d+)\)\s+VLAN:\s+(\d+)", line)
                    if match:
                        mac_address = match.group(1)
                        port = int(match.group(2))
                        vlan = int(match.group(3))
                        mac_tables[switch_name].append({
                            "mac_address": mac_address,
                            "vlan": vlan,
                            "port": port,
                        })
    return mac_tables

# The rest of the code (load_topology, build_graph, visualize_network, and the main block) remains the same.

def load_topology(topology_file):
    with open(topology_file, "r") as f:
        topology = yaml.safe_load(f)
    return topology

def build_graph(topology, mac_tables):
    graph = nx.Graph()

    # Add switches and inter-switch links
    inter_switch_ports = {}  # Store inter-switch ports for each switch
    for link in topology["links"]:
        src_switch = link["src_switch"]
        dst_switch = link["dst_switch"]
        src_port = link["src_port"]
        dst_port = link["dst_port"]

        if src_switch not in graph:
            graph.add_node(src_switch, type="switch")
            inter_switch_ports[src_switch] = set()
        if dst_switch not in graph:
            graph.add_node(dst_switch, type="switch")
            inter_switch_ports[dst_switch] = set()

        graph.add_edge(src_switch, dst_switch,
                      src_port=src_port, dst_port=dst_port)
        inter_switch_ports[src_switch].add(src_port)
        inter_switch_ports[dst_switch].add(dst_port)

    vlan_colors = {}
    next_color_index = 0
    colors = list(mcolors.TABLEAU_COLORS.values())

    # Add end devices from MAC tables, filtering based on inter-switch ports
    for switch, entries in mac_tables.items():
        for entry in entries:
            mac_address = entry["mac_address"]
            vlan = entry["vlan"]
            port = entry["port"]

            # Skip if the port matches an inter-switch link port on this switch
            if switch in inter_switch_ports and port in inter_switch_ports[switch]:
                continue

            device_name = f"Device-{mac_address[-4:]}"
            if device_name not in graph:
                graph.add_node(device_name,
                               type="device",
                               mac_address=mac_address,
                               vlan=vlan)
                if vlan not in vlan_colors:
                    vlan_colors[vlan] = colors[next_color_index % len(colors)]
                    next_color_index += 1
            # Add edge only if the device node exists (to handle cases where the MAC is seen on multiple non-interlink ports)
            if device_name in graph and not graph.has_edge(switch, device_name):
                graph.add_edge(switch, device_name, port=port)

    # Detect VLAN leakage (this part remains largely the same)
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
    pos = nx.spring_layout(graph, k=0.3, iterations=50)

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
            node_colors.append(vlan_colors.get(vlan, "gray"))
            node_sizes.append(400)
            if "leaky_vlans" in attrs:
                node_borders.append("red")
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

    edge_labels = {}
    for u, v, data in graph.edges(data=True):
        label = ""
        if "src_port" in data and "dst_port" in data:
            label = f"{data['src_port']}-{data['dst_port']}"
        elif "port" in data:
            label = str(data["port"])
        edge_labels[(u, v)] = label
    nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, font_size=6)

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
    mac_table_dir = "mac_results"

    mac_tables = parse_mac_tables(mac_table_dir)
    topology = load_topology(topology_file)
    graph, vlan_colors = build_graph(topology, mac_tables)
    visualize_network(graph, vlan_colors)