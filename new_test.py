import os
import yaml
import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict

# Load topology data
with open('topology.yaml', 'r') as file:
    topology = yaml.safe_load(file)

switch_connections = {}
for link in topology['links']:
    switch_connections[(link['source'], link['source_port'])] = (link['destination'], link['destination_port'])
    switch_connections[(link['destination'], link['destination_port'])] = (link['source'], link['source_port'])

# Parse MAC tables from files
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

# Resolve primary switch for each MAC address
device_location = {}
for mac, locations in mac_tables.items():
    for switch_name, port, vlan in locations:
        if (switch_name, port) in switch_connections:
            other_switch, _ = switch_connections[(switch_name, port)]
            if mac in mac_tables and any(l[0] == other_switch for l in mac_tables[mac]):
                continue
        if mac not in device_location:
            device_location[mac] = (switch_name, port, vlan)

# Visualize using NetworkX
G = nx.Graph()

for switch in topology['switches']:
    G.add_node(switch['name'], type='switch')

for (src, src_port), (dst, dst_port) in switch_connections.items():
    G.add_edge(src, dst, label=f'{src_port} <-> {dst_port}')

for mac, (switch, port, vlan) in device_location.items():
    G.add_node(mac, type='device')
    G.add_edge(switch, mac, label=f'Port {port} (VLAN {vlan})')
# Ensure all nodes have a 'type' attribute
for n in G.nodes():
    if 'type' not in G.nodes[n]:
        G.nodes[n]['type'] = 'unknown'
print("Nodes in the graph:", G.nodes(data=True))
# Draw the network
pos = nx.spring_layout(G)
plt.figure(figsize=(10, 8))
nx.draw(G, pos, with_labels=True, node_color=['lightblue' if G.nodes[n]['type'] == 'switch' else 'lightgreen' for n in G.nodes()])
edge_labels = nx.get_edge_attributes(G, 'label')
nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
plt.title('Network Topology with MAC Addresses')
plt.show()