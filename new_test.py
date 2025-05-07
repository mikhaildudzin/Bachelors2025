import os
import yaml
import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict
import matplotlib.colors as mcolors

# ==============================
# STEP 1: Load Topology Data
# ==============================
with open('topology.yaml', 'r') as file:
    topology = yaml.safe_load(file)

# Build switch connections from topology data
switch_connections = {}
for link in topology['links']:
    switch_connections[(link['source'], link['source_port'])] = (link['destination'], link['destination_port'])
    switch_connections[(link['destination'], link['destination_port'])] = (link['source'], link['source_port'])

# ==============================
# STEP 2: Parse MAC Tables
# ==============================
mac_tables = defaultdict(list)
for filename in os.listdir():
    if filename.endswith('.txt') and filename != 'topology.yml':
        switch_name = filename.replace('.txt', '')
        with open(filename, 'r') as f:
            for line in f:
                if '(port:' in line:
                    parts = line.strip().split()
                    mac_address = parts[0]
                    port = parts[2].strip(')')
                    vlan = parts[4]
                    mac_tables[mac_address].append((switch_name, port, vlan))

# ==============================
# STEP 3: Resolve Primary Switch for Each MAC
# ==============================
device_location = {}
for mac, locations in mac_tables.items():
    for switch_name, port, vlan in locations:
        if (switch_name, port) in switch_connections:
            other_switch, _ = switch_connections[(switch_name, port)]
            if mac in mac_tables and any(l[0] == other_switch for l in mac_tables[mac]):
                continue
        if mac not in device_location:
            device_location[mac] = (switch_name, port, vlan)

# ==============================
# STEP 4: Build Graph Topology
# ==============================
G = nx.Graph()

# Add switch nodes
for switch in topology['switches']:
    G.add_node(switch['name'], type='switch')

# Add links between switches
for (src, src_port), (dst, dst_port) in switch_connections.items():
    G.add_edge(src, dst, label=f'{src_port} <-> {dst_port}', color='gray')

# Add device nodes and edges to their primary switch
color_keys = list(mcolors.CSS4_COLORS.keys())
for mac, (switch, port, vlan) in device_location.items():
    G.add_node(mac, type='device')
    color = mcolors.CSS4_COLORS[color_keys[(int(vlan) * 7) % len(color_keys)]]
    G.add_edge(switch, mac, label=f'Port {port} (VLAN {vlan})', color=color)

# Ensure all nodes have a 'type' attribute
for n in G.nodes():
    if 'type' not in G.nodes[n]:
        G.nodes[n]['type'] = 'unknown'

# ==============================
# STEP 5: Visualize the Network
# ==============================
# Generate unique colors for each VLAN
vlans = {vlan for _, (_, _, vlan) in device_location.items()}
vlan_colors = {vlan: mcolors.CSS4_COLORS[color_keys[(int(vlan) * 7) % len(color_keys)]] for vlan in vlans}

# Define colors for each node
node_colors = []
for n in G.nodes():
    if G.nodes[n]['type'] == 'switch':
        node_colors.append('lightblue')
    elif G.nodes[n]['type'] == 'device':
        _, _, vlan = device_location.get(n, (None, None, None))
        node_colors.append(vlan_colors.get(vlan, 'lightgreen'))
    else:
        node_colors.append('gray')

# Draw the network
pos = nx.spring_layout(G)
plt.figure(figsize=(10, 8))
edge_colors = [G[u][v]['color'] for u, v in G.edges()]
nx.draw(G, pos, with_labels=True, node_color=node_colors, edge_color=edge_colors, node_size=500)
edge_labels = nx.get_edge_attributes(G, 'label')
nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)

# Add legend for VLANs
for vlan, color in vlan_colors.items():
    plt.scatter([], [], c=[color], label=f'VLAN {vlan}')
plt.legend(loc='upper left', title='VLANs')
plt.title('Network Topology with VLAN Coloring')
plt.show()
