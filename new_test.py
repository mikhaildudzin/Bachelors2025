import yaml
import networkx as nx
import matplotlib.pyplot as plt
import os
from io import StringIO

# Load switch data from files in a directory
def load_switch_data_from_dir(directory):
    switch_data = {}
    for filename in os.listdir(directory):
        if filename.startswith("SW") and filename.endswith(".txt"):
            file_path = os.path.join(directory, filename)
            with open(file_path, 'r') as file:
                data = file.read()
            switch_name = data.split('\n')[0].split(':')[1].strip().split(' ')[0]
            mac_table = {}
            for line in data.split('\n')[1:]:
                if line.strip():
                    mac, port_vlan = line.split('(')
                    mac = mac.strip()
                    port = int(port_vlan.split('port:')[1].split(')')[0])
                    mac_table[mac] = port
            switch_data[switch_name] = mac_table
    return switch_data

# Load topology data
def load_topology_data(file_path):
    with open(file_path, 'r') as file:
        topology = yaml.safe_load(file)
    return topology['links']

# Directory containing switch files
switch_data_dir = 'mac_results'  # Current directory, change as needed
switch_data = load_switch_data_from_dir(switch_data_dir)
topology = load_topology_data('topology.yaml')

# Create the graph
G = nx.Graph()

# Add switches as nodes
for switch_name in switch_data.keys():
    G.add_node(switch_name, type='switch')

# Helper function to check if a MAC is an end device
def is_end_device(mac, switch_tables, topology):
    connected_ports = []
    for switch, table in switch_tables.items():
        if mac in table:
            port = table[mac]
            connected_ports.append((switch, port))

    if len(connected_ports) > 1:  # Check if MAC appears on multiple switches
        return False
    if len(connected_ports) == 0:
        return False
    return True

# Add links between switches
for link in topology:
    src_switch = link['src_switch']
    dst_switch = link['dst_switch']
    if src_switch in G.nodes and dst_switch in G.nodes:
        G.add_edge(src_switch, dst_switch)

# Add end devices
end_devices = {}
for switch, table in switch_data.items():
    for mac, port in table.items():
        if is_end_device(mac, switch_data, topology):
            G.add_node(mac, type='host')
            G.add_edge(switch, mac)
            end_devices[mac] = switch

# Visualization
pos = nx.spring_layout(G, k=0.8)

# Node colors based on type
node_colors = [
    'skyblue' if G.nodes[node]['type'] == 'switch' else 'lightgreen'
    for node in G.nodes
]

# Draw nodes
nx.draw(G, pos, with_labels=True, node_color=node_colors, node_size=2000, font_size=10, font_weight='bold')

# Draw edges
nx.draw_networkx_edges(G, pos, edge_color='gray')

plt.title("Network Topology with End Devices")
plt.show()